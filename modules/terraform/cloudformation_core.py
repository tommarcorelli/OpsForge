"""
modules/terraform/cloudformation_core.py
-----------------------------------------
Export alternatif du module Terraform d'OpsForge : au lieu d'un `main.tf`
(HCL), genere un template **AWS CloudFormation** (YAML) a partir d'une
config du meme esprit (liste de ressources + parametres + outputs).

CloudFormation n'est pas multi-cloud (contrairement a Terraform) : ce
generateur est donc volontairement **AWS uniquement**, avec son propre
catalogue de types de ressources CFN (AWS::Service::Resource), distinct
du RESOURCE_CATALOG Terraform de core.py (types et noms de proprietes
differents, ex: `instance_type` cote Terraform vs `InstanceType` cote CFN).

Reference entre ressources : une valeur de propriete prefixee par '=' est
traitee comme une **intrinsic function CloudFormation** en syntaxe courte
(ex: "=!Ref WebServerSG" -> !Ref WebServerSG, "=!GetAtt Web.PublicIp" ->
!GetAtt Web.PublicIp), sur le meme principe que l'echappatoire '=' de
core.py pour les references Terraform.

Usage basique :
    from modules.terraform.cloudformation_core import generate_cloudformation

    config = {
        "resources": [
            {"type": "AWS::S3::Bucket", "name": "SiteBucket",
             "properties": {"BucketName": "mon-site-statique-123"}},
        ],
    }
    yaml_text = generate_cloudformation(config)
"""

import json
import os
import re

import yaml

# ---------------------------------------------------------------------------
# Catalogue des types de ressources CloudFormation pris en charge.
# required : proprietes obligatoires (validation). template : valeurs
# d'exemple pretes a l'emploi.
# ---------------------------------------------------------------------------
RESOURCE_CATALOG = [
    {"type": "AWS::EC2::Instance", "label": "Instance EC2",
     "required": ["ImageId", "InstanceType"],
     "template": {"ImageId": "ami-0abcdef1234567890", "InstanceType": "t3.micro",
                  "Tags": [{"Key": "Name", "Value": "serveur-web"}]}},
    {"type": "AWS::S3::Bucket", "label": "Bucket S3",
     "required": [],
     "template": {"BucketName": "mon-bucket-unique-123"}},
    {"type": "AWS::EC2::SecurityGroup", "label": "Security Group",
     "required": ["GroupDescription"],
     "template": {"GroupDescription": "Autorise HTTP/HTTPS",
                  "SecurityGroupIngress": [
                      {"IpProtocol": "tcp", "FromPort": 80, "ToPort": 80, "CidrIp": "0.0.0.0/0"},
                      {"IpProtocol": "tcp", "FromPort": 443, "ToPort": 443, "CidrIp": "0.0.0.0/0"},
                  ]}},
    {"type": "AWS::EC2::VPC", "label": "VPC",
     "required": ["CidrBlock"],
     "template": {"CidrBlock": "10.0.0.0/16", "Tags": [{"Key": "Name", "Value": "main"}]}},
    {"type": "AWS::EC2::Subnet", "label": "Subnet",
     "required": ["VpcId", "CidrBlock"],
     "template": {"VpcId": "=!Ref MainVPC", "CidrBlock": "10.0.1.0/24"}},
    {"type": "AWS::EC2::InternetGateway", "label": "Internet Gateway",
     "required": [],
     "template": {"Tags": [{"Key": "Name", "Value": "main-igw"}]}},
    {"type": "AWS::EC2::VPCGatewayAttachment", "label": "Attachement VPC <-> Internet Gateway",
     "required": ["VpcId", "InternetGatewayId"],
     "template": {"VpcId": "=!Ref MainVPC", "InternetGatewayId": "=!Ref MainIGW"}},
    {"type": "AWS::EC2::RouteTable", "label": "Table de routage",
     "required": ["VpcId"],
     "template": {"VpcId": "=!Ref MainVPC", "Tags": [{"Key": "Name", "Value": "public"}]}},
    {"type": "AWS::EC2::Route", "label": "Route",
     "required": ["RouteTableId", "DestinationCidrBlock"],
     "template": {"RouteTableId": "=!Ref PublicRouteTable", "DestinationCidrBlock": "0.0.0.0/0",
                  "GatewayId": "=!Ref MainIGW"}},
    {"type": "AWS::EC2::SubnetRouteTableAssociation", "label": "Association route table",
     "required": ["SubnetId", "RouteTableId"],
     "template": {"SubnetId": "=!Ref PublicSubnet", "RouteTableId": "=!Ref PublicRouteTable"}},
    {"type": "AWS::RDS::DBInstance", "label": "Base RDS",
     "required": ["AllocatedStorage", "DBInstanceClass", "Engine", "MasterUsername", "MasterUserPassword"],
     "template": {"AllocatedStorage": "20", "DBInstanceClass": "db.t3.micro", "Engine": "postgres",
                  "MasterUsername": "admin", "MasterUserPassword": "=!Ref DBPassword",
                  "DBName": "app"}},
    {"type": "AWS::IAM::Role", "label": "Role IAM",
     "required": ["AssumeRolePolicyDocument"],
     "template": {"AssumeRolePolicyDocument": {
         "Version": "2012-10-17",
         "Statement": [{"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"},
                        "Action": "sts:AssumeRole"}],
     }}},
    {"type": "AWS::Lambda::Function", "label": "Fonction Lambda",
     "required": ["Code", "Handler", "Role", "Runtime"],
     "template": {"Code": {"S3Bucket": "mon-bucket-lambda", "S3Key": "lambda.zip"},
                  "Handler": "index.handler", "Role": "=!GetAtt AppRole.Arn",
                  "Runtime": "python3.12"}},
]


def _catalog_index():
    return {entry["type"]: entry for entry in RESOURCE_CATALOG}


# ---------------------------------------------------------------------------
# Presets prets a l'emploi (AWS uniquement, CloudFormation n'a pas de
# notion multi-provider).
# ---------------------------------------------------------------------------
PRESETS = {
    "ec2-web": {
        "label": "EC2 + Security Group (web)",
        "config": {
            "resources": [
                {"type": "AWS::EC2::SecurityGroup", "name": "WebSG",
                 "properties": {"GroupDescription": "Autorise HTTP/HTTPS"}},
                {"type": "AWS::EC2::Instance", "name": "WebServer", "properties": {
                    "ImageId": "ami-0abcdef1234567890", "InstanceType": "t3.micro",
                    "SecurityGroupIds": ["=!Ref WebSG"],
                    "Tags": [{"Key": "Name", "Value": "serveur-web"}]}},
            ],
            "outputs": {"PublicIp": {"Value": "=!GetAtt WebServer.PublicIp"}},
        },
    },
    "s3-static": {
        "label": "Bucket S3 (site statique)",
        "config": {
            "resources": [
                {"type": "AWS::S3::Bucket", "name": "SiteBucket",
                 "properties": {"BucketName": "mon-site-statique-123"}},
            ],
        },
    },
    "vpc-basic": {
        "label": "VPC + subnet public + Internet Gateway",
        "config": {
            "resources": [
                {"type": "AWS::EC2::VPC", "name": "MainVPC",
                 "properties": {"CidrBlock": "10.0.0.0/16", "Tags": [{"Key": "Name", "Value": "main"}]}},
                {"type": "AWS::EC2::Subnet", "name": "PublicSubnet", "properties": {
                    "VpcId": "=!Ref MainVPC", "CidrBlock": "10.0.1.0/24"}},
                {"type": "AWS::EC2::InternetGateway", "name": "MainIGW", "properties": {}},
                {"type": "AWS::EC2::VPCGatewayAttachment", "name": "GatewayAttachment", "properties": {
                    "VpcId": "=!Ref MainVPC", "InternetGatewayId": "=!Ref MainIGW"}},
                {"type": "AWS::EC2::RouteTable", "name": "PublicRouteTable",
                 "properties": {"VpcId": "=!Ref MainVPC"}},
                {"type": "AWS::EC2::Route", "name": "PublicRoute", "properties": {
                    "RouteTableId": "=!Ref PublicRouteTable", "DestinationCidrBlock": "0.0.0.0/0",
                    "GatewayId": "=!Ref MainIGW"}},
                {"type": "AWS::EC2::SubnetRouteTableAssociation", "name": "PublicAssociation", "properties": {
                    "SubnetId": "=!Ref PublicSubnet", "RouteTableId": "=!Ref PublicRouteTable"}},
            ],
            "outputs": {
                "VpcId": {"Value": "=!Ref MainVPC"},
                "SubnetId": {"Value": "=!Ref PublicSubnet"},
            },
        },
    },
    "rds-postgres": {
        "label": "Base RDS PostgreSQL + Security Group",
        "config": {
            "parameters": {
                "DBPassword": {"Type": "String", "NoEcho": True, "Description": "Mot de passe de la base"},
            },
            "resources": [
                {"type": "AWS::EC2::SecurityGroup", "name": "DBSG",
                 "properties": {"GroupDescription": "Autorise Postgres depuis le VPC"}},
                {"type": "AWS::RDS::DBInstance", "name": "AppDB", "properties": {
                    "AllocatedStorage": "20", "DBInstanceClass": "db.t3.micro", "Engine": "postgres",
                    "MasterUsername": "admin", "MasterUserPassword": "=!Ref DBPassword",
                    "DBName": "app", "VPCSecurityGroups": ["=!Ref DBSG"]}},
            ],
            "outputs": {"Endpoint": {"Value": "=!GetAtt AppDB.Endpoint.Address"}},
        },
    },
}


def obtenir_preset(nom):
    if nom not in PRESETS:
        raise KeyError(nom)
    return json.loads(json.dumps(PRESETS[nom]["config"]))


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
_LOGICAL_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")


def valider_config(config):
    """Retourne (erreurs, avertissements) sans lever d'exception."""
    erreurs = []
    avertissements = []
    config = config or {}

    idx = _catalog_index()
    resources = config.get("resources") or []
    if not resources:
        avertissements.append("Aucune ressource : le template ne contiendra qu'un squelette vide.")

    noms_vus = set()
    for i, res in enumerate(resources):
        rtype = res.get("type")
        rname = res.get("name")
        etiquette = f"Ressource #{i + 1}"
        if not rtype:
            erreurs.append(f"{etiquette} : champ « type » manquant.")
            continue
        if not rname:
            erreurs.append(f"{etiquette} ({rtype}) : champ « name » manquant.")
            continue
        if not _LOGICAL_ID_RE.match(rname):
            erreurs.append(
                f"{etiquette} : « {rname} » n'est pas un identifiant logique CloudFormation valide "
                "(lettres/chiffres uniquement, doit commencer par une lettre)."
            )
        if rname in noms_vus:
            erreurs.append(f"{etiquette} : le nom logique « {rname} » est defini en double.")
        noms_vus.add(rname)

        entry = idx.get(rtype)
        if entry:
            props = res.get("properties") or {}
            manquantes = [p for p in entry["required"] if p not in props]
            if manquantes:
                erreurs.append(f"{rtype}.{rname} : propriete(s) requise(s) manquante(s) : {', '.join(manquantes)}.")
        else:
            avertissements.append(f"{rtype} : type non catalogue — genere sans validation des proprietes.")

    return erreurs, avertissements


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------
class _Intrinsic(str):
    """Marqueur pour une valeur emise en syntaxe courte d'intrinsic
    function CloudFormation (!Ref, !GetAtt, !Sub...) plutot que comme une
    chaine YAML classique."""


def _represent_intrinsic(dumper, data):
    tag, _, rest = data.partition(" ")
    return dumper.represent_scalar(tag, rest)


yaml.add_representer(_Intrinsic, _represent_intrinsic)

_INTRINSIC_QUOTES_RE = re.compile(r"(![A-Za-z]+) '([^']*)'")


def _convert_value(value):
    """Convertit recursivement une valeur de config : une chaine prefixee
    par '=' devient une intrinsic function CFN (le reste de la chaine est
    suppose deja au format '!Ref Xxx' / '!GetAtt Xxx.Yyy' / etc.)."""
    if isinstance(value, str):
        if value.startswith("="):
            return _Intrinsic(value[1:])
        return value
    if isinstance(value, list):
        return [_convert_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _convert_value(v) for k, v in value.items()}
    return value


def generate_cloudformation(config):
    """Construit un template CloudFormation (YAML) a partir de la config.
    Leve ValueError si la config est invalide."""
    config = config or {}
    erreurs, _ = valider_config(config)
    if erreurs:
        raise ValueError(" ; ".join(erreurs))

    template = {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": config.get("description") or "Genere par OpsForge (module Terraform - export CloudFormation)",
    }

    parameters = config.get("parameters") or {}
    if parameters:
        template["Parameters"] = _convert_value(parameters)

    resources_out = {}
    for res in config.get("resources") or []:
        resources_out[res["name"]] = {
            "Type": res["type"],
            "Properties": _convert_value(res.get("properties") or {}),
        }
    template["Resources"] = resources_out

    outputs = config.get("outputs") or {}
    if outputs:
        template["Outputs"] = _convert_value(outputs)

    text = yaml.dump(template, default_flow_style=False, sort_keys=False, width=100)
    text = _INTRINSIC_QUOTES_RE.sub(r"\1 \2", text)
    return text


def write_cloudformation(config, output_path):
    contenu = generate_cloudformation(config)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(contenu)
    return output_path
