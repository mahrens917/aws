#!/usr/bin/env python3
"""
AWS VM Import Service Role Setup Script
Creates the required 'vmimport' IAM service role needed for AMI export operations.
This role is required by AWS to export AMIs to S3.
"""

import json
import os
import sys

import boto3
from botocore.exceptions import ClientError

from cost_toolkit.common.credential_utils import setup_aws_credentials


def get_trust_policy():
    """Return trust policy for vmimport role"""
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "vmie.amazonaws.com"},
                "Action": "sts:AssumeRole",
                "Condition": {"StringEquals": {"sts:Externalid": "vmimport"}},
            }
        ],
    }


def get_vmimport_policy():
    """Return permissions policy for vmimport role"""
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "s3:GetBucketLocation",
                    "s3:GetObject",
                    "s3:ListBucket",
                    "s3:PutObject",
                    "s3:GetBucketAcl",
                ],
                "Resource": ["arn:aws:s3:::*"],
            },
            {
                "Effect": "Allow",
                "Action": [
                    "ec2:ModifySnapshotAttribute",
                    "ec2:CopySnapshot",
                    "ec2:RegisterImage",
                    "ec2:Describe*",
                ],
                "Resource": "*",
            },
        ],
    }


def create_new_role_with_policy(iam_client, trust_policy, vmimport_policy):
    """Create a new vmimport role and attach policy"""
    print("🔄 Creating vmimport service role...")

    # Create the role
    role_response = iam_client.create_role(
        RoleName="vmimport",
        AssumeRolePolicyDocument=json.dumps(trust_policy),
        Description="Service role for VM Import/Export operations",
    )

    print(f"✅ Created vmimport role: {role_response['Role']['Arn']}")

    # Create and attach the policy
    print("🔄 Creating vmimport policy...")

    policy_response = iam_client.create_policy(
        PolicyName="vmimport-policy",
        PolicyDocument=json.dumps(vmimport_policy),
        Description="Policy for VM Import/Export operations",
    )

    print(f"✅ Created vmimport policy: {policy_response['Policy']['Arn']}")

    # Attach policy to role
    print("🔄 Attaching policy to role...")

    iam_client.attach_role_policy(RoleName="vmimport", PolicyArn=policy_response["Policy"]["Arn"])

    print("✅ Successfully attached policy to vmimport role")
    print()
    print("🎉 VM Import service role setup completed!")
    print("   You can now run the S3 export script successfully.")


def print_alternative_setup_instructions():
    """Print AWS CLI alternative setup instructions"""
    print("💡 Alternative setup using AWS CLI:")
    print("1. Create trust policy file:")
    print(
        '   echo \'{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"vmie.amazonaws.com"},"Action":"sts:AssumeRole","Condition":{"StringEquals":{"sts:Externalid":"vmimport"}}}]}\' > trust-policy.json'
    )
    print()
    print("2. Create the role:")
    print("   aws iam create-role --role-name vmimport --assume-role-policy-document file://trust-policy.json")
    print()
    print("3. Create policy file:")
    print(
        '   echo \'{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["s3:GetBucketLocation","s3:GetObject","s3:ListBucket","s3:PutObject","s3:GetBucketAcl"],"Resource":["arn:aws:s3:::*"]},{"Effect":"Allow","Action":["ec2:ModifySnapshotAttribute","ec2:CopySnapshot","ec2:RegisterImage","ec2:Describe*"],"Resource":"*"}]}\' > role-policy.json'
    )
    print()
    print("4. Attach policy:")
    print("   aws iam put-role-policy --role-name vmimport --policy-name vmimport --policy-document file://role-policy.json")


def create_vmimport_role():
    """Create the vmimport service role required for AMI exports"""
    env_path = os.path.expanduser("~/.env")
    aws_access_key_id, aws_secret_access_key = setup_aws_credentials(env_path)

    # Create IAM client
    iam_client = boto3.client(
        "iam",
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
    )

    print("AWS VM Import Service Role Setup")
    print("=" * 50)
    print("Setting up the required 'vmimport' IAM service role for AMI exports...")
    print()

    trust_policy = get_trust_policy()
    vmimport_policy = get_vmimport_policy()

    try:
        # Check if role already exists
        try:
            role = iam_client.get_role(RoleName="vmimport")
            print("✅ vmimport role already exists")
            print(f"   Role ARN: {role['Role']['Arn']}")
            print(f"   Created: {role['Role']['CreateDate']}")
        except iam_client.exceptions.NoSuchEntityException:
            create_new_role_with_policy(iam_client, trust_policy, vmimport_policy)

    except ClientError as e:
        print(f"❌ Error setting up vmimport role: {e}")
        print()
        print_alternative_setup_instructions()
        return False
    return True


def main():
    """Main function."""
    try:
        create_vmimport_role()
    except ClientError as e:
        print(f"❌ Script failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
