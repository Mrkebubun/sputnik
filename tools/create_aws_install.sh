#!/bin/bash
export AWS_ACCESS_KEY=
export AWS_SECRET_KEY=
export AWS_DEFAULT_REGION=us-west-2
export AWS_DEFAULT_OUTPUT=text
DOMAIN=testcustomer.com

# Create a VPC for this exchange
VPC_ID=`aws ec2 create-vpc --cidr-block "10.0.0.0/16" | awk '{ print $6 }'`

# Create security groups
# Open to the internet
WSSG_ID=`aws ec2 create-security-group --group-name $DOMAIN-ws --vpc-id $VPC_ID --description "Web Security Group" | awk '{ print $1 }'

# Open to just the app servers
DBSG_ID=`aws ec2 create-security-group --group-name $DOMAIN-db --vpc-id $VPC_ID --description "DB Security Group" | awk '{ print $1 }'

# Open just to the webservers and each other
APPSG_ID=`aws ec2 create-security-group --group-name $DOMAIN-app --vpc-id $VPC_ID --description "App Security Group" | awk '{ print $1 }'

# Create an AWS that has the Sputnik Image
aws ec2 run-instances --image-id ${IMAGE_ID} --count 1 --instance-type t1.micro --key-name default --security-groups $WSSG_ID \