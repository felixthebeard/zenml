# AWS Cloud Guide

This step-by-step guide explains how to set up and configure all the infrastructure necessary to run a ZenML pipeline on AWS.

## Prerequisites

- [Docker](https://www.docker.com/) installed and running.
- [kubectl](https://kubernetes.io/docs/tasks/tools/) installed.
- The [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) installed and authenticated.
- ZenML and the integrations for this tutorial stack installed:
    ```shell
    pip install zenml
    zenml integration install aws s3 kubernetes
    ```

## Setting up the AWS resources

Let's open up a terminal which we'll use to store some values along the way which we'll need to configure our ZenML stack later.

### Artifact Store (S3 bucket)

{% tabs %}
{% tab title="AWS UI" %}

- Go to the [S3 website](https://s3.console.aws.amazon.com/s3/buckets).
- Click on `Create bucket`.
- Select a descriptive name and a region. Let's also set these as environment variables in our terminal:
    ```shell
    REGION=<REGION> # for example us-west-1
    S3_BUCKET_NAME=<BUCKET_NAME>
    ```

{% tab title="AWS CLI" %}

```shell
# Replace the <PLACEHOLDERS> with a name for your bucket and the AWS region for your resources
# Select one of the region codes for <REGION>: https://docs.aws.amazon.com/general/latest/gr/rande.html#regional-endpoints
REGION=<REGION>  
S3_BUCKET_NAME=<S3_BUCKET_NAME>

aws s3api create-bucket --bucket=$S3_BUCKET_NAME \
    --region=$REGION \
    --create-bucket-configuration=LocationConstraint=$REGION
```

{% endtab %}
{% endtabs %}

### Metadata Store (RDS MySQL database)

{% tabs %}
{% tab title="AWS UI" %}

- Go to the [RDS website](https://console.aws.amazon.com/rds).
- Make sure the correct region is selected on the top right (this region must be the same for all following steps).
- Click on `Create database`.
- Select `Easy Create`, `MySQL`, `Free tier` and enter values for your database name, username and password.
- Note down the username and password:
    ```shell
    RDS_MYSQL_USERNAME=<RDS_MYSQL_USERNAME>
    RDS_MYSQL_PASSWORD=<RDS_MYSQL_PASSWORD>
    ```
- Wait until the deployment is finished.
- Select your new database and note down its endpoint:
    ```shell
    RDS_MYSQL_ENDPOINT=<RDS_MYSQL_ENDPOINT>
    ```
- Click on the active VPC security group, select `Inbound rules` and click on `Edit inbound rules`
- Add a new rule with type `MYSQL/Aurora` and source `Anywhere-IPv4`.
- Go back to your database page and click on `Modify` in the top right.
- In the `Connectivity` section, open the `Advanced configuration` and enable public access.

{% tab title="AWS CLI" %}

```shell
# Set values for your database id and username/password to access it
MYSQL_DATABASE_ID=<MYSQL_DATABASE_ID>
RDS_MYSQL_USERNAME=<RDS_MYSQL_USERNAME>
RDS_MYSQL_PASSWORD=<RDS_MYSQL_PASSWORD>

aws rds create-db-instance --engine=mysql \
    --db-instance-class=db.t3.micro \
    --allocated-storage 20 \
    --publicly-accessible \
    --db-instance-identifier=$MYSQL_DATABASE_ID \
    --region=$REGION \
    --master-username=$RDS_MYSQL_USERNAME \
    --master-user-password=$RDS_MYSQL_PASSWORD

# Fetch the endpoint for later
RDS_MYSQL_ENDPOINT=$(aws rds describe-db-instances --query='DBInstances[0].Endpoint.Address' \
    --output=text \
    --db-instance-identifier=$MYSQL_DATABASE_ID \
    --region=$REGION)

# Fetch the security group id
SECURITY_GROUP_ID=$(aws rds describe-db-instances --query='DBInstances[0].VpcSecurityGroups[0].VpcSecurityGroupId' \
    --output=text
    --db-instance-identifier=$MYSQL_DATABASE_ID \
    --region=$REGION)

aws ec2 authorize-security-group-ingress \
    --protocol=tcp \
    --port=3306 \
    --cidr=0.0.0.0/0 \
    --group-id=$SECURITY_GROUP_ID \
    --region=$REGION
```

{% endtab %}
{% endtabs %}

### Container Registry (ECR)

{% tabs %}
{% tab title="AWS UI" %}

- Go to the [ECR website](https://console.aws.amazon.com/ecr).
- Make sure the correct region is selected on the top right.
- Click on `Create repository`.
- Create a private repository called `zenml-kubernetes` with default settings.
- Note down the URI of your registry:
    ```shell
    # This should be the prefix of your just created repository URI, 
    # e.g. 714803424590.dkr.ecr.eu-west-1.amazonaws.com
    ECR_URI=<ECR_URI>
    ```

{% tab title="AWS CLI" %}

```shell
aws ecr create-repository --repository-name=zenml-kubernetes --region=$REGION

REGISTRY_ID=$(aws ecr describe-registry --region=$REGION --query=registryId --output=text)
ECR_URI="$REGISTRY_ID.dkr.ecr.$REGION.amazonaws.com"
```

{% endtab %}
{% endtabs %}

### Orchestrator (EKS)

{% tabs %}
{% tab title="AWS UI" %}

- Follow [this guide](https://docs.aws.amazon.com/eks/latest/userguide/service_IAM_role.html#create-service-role) to create an Amazon EKS cluster role.
- Go to the [IAM website](https://console.aws.amazon.com/iam), select `Roles` and edit the role you just created.
- Click on `Add permissions` and select `Attach policies`.
- Attach the `SecretsManagerReadWrite`, and `AmazonS3FullAccess` policies to the role.
- Go to the [EKS website](https://console.aws.amazon.com/eks).
- Make sure the correct region is selected on the top right.
- Click on `Add cluster` and select `Create`.
- Enter a name and select our just created role for `Cluster service role`.
- Keep the default values for the networking and logging steps and create the cluster.
- Note down the cluster name:
    ```shell
    EKS_CLUSTER_NAME=<EKS_CLUSTER_NAME>
    ```
- After the cluster is created, select it and click on `Add node group` in the `Compute` tab.
- Enter a name and select the `EKSNodeRole`.
- Keep all other default values and create the node group.

{% tab title="AWS CLI" %}

```shell
EKS_ROLE_NAME=<EKS_ROLE_NAME>
EC2_ROLE_NAME=<EC2_ROLE_NAME>

# Choose a name for your EKS cluster and node group
EKS_CLUSTER_NAME=<EKS_CLUSTER_NAME>
NODEGROUP_NAME=<NODEGROUP_NAME>

EKS_POLICY_JSON='{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "eks.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}'
aws iam create-role \
    --role-name=$EKS_ROLE_NAME \
    --assume-role-policy-document=$EKS_POLICY_JSON

aws iam attach-role-policy \
    --policy-arn='arn:aws:iam::aws:policy/AmazonEKSClusterPolicy' \
    --role-name=$EKS_ROLE_NAME


EC2_POLICY_JSON='{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ec2.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}'
aws iam create-role \
    --role-name=$EC2_ROLE_NAME \
    --assume-role-policy-document=$EC2_POLICY_JSON
aws iam attach-role-policy \
    --policy-arn='arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy' \
    --role-name=$EC2_ROLE_NAME
aws iam attach-role-policy \
    --policy-arn='arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly' \
    --role-name=$EC2_ROLE_NAME
aws iam attach-role-policy \
    --policy-arn='arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy' \
    --role-name=$EC2_ROLE_NAME
aws iam attach-role-policy \
    --policy-arn='arn:aws:iam::aws:policy/SecretsManagerReadWrite' \
    --role-name=$EC2_ROLE_NAME
aws iam attach-role-policy \
    --policy-arn='arn:aws:iam::aws:policy/AmazonS3FullAccess' \
    --role-name=$EC2_ROLE_NAME


# Get the role ARN's
EKS_ROLE_ARN=$(aws iam get-role --role-name=$EKS_ROLE_NAME --query='Role.Arn' --output=text)
EC2_ROLE_ARN=$(aws iam get-role --role-name=$EC2_ROLE_NAME --query='Role.Arn' --output=text)


# Get default VPC ID
VPC_ID=$(aws ec2 describe-vpcs --filters='Name=is-default,Values=true' \
    --query='Vpcs[0].VpcId' \
    --output=text \
    --region=$REGION)

# Get subnet IDs
SUBNET_IDS=$(aws ec2 describe-subnets --region=$REGION \
    --filters="Name=vpc-id,Values=$VPC_ID" \
    --query='Subnets[*].SubnetId' \
    --output=json)

aws eks create-cluster --region=$REGION \
    --name=$EKS_CLUSTER_NAME \
    --role-arn=$EKS_ROLE_ARN \
    --resources-vpc-config="{\"subnetIds\": $SUBNET_IDS}"

# Wait until the cluster is created and then run
aws eks create-nodegroup --region=$REGION \
    --cluster-name=$EKS_CLUSTER_NAME \
    --nodegroup-name=$NODEGROUP_NAME \
    --node-role=$EC2_ROLE_ARN \
    --subnets=$SUBNET_IDS
```

{% endtab %}
{% endtabs %}

## Register the ZenML stack

- Register the artifact store:
    ```shell
    zenml artifact-store register s3_store \
        --flavor=s3 \
        --path=s3://$S3_BUCKET_NAME
    ```

- Register the container registry and authenticate your local docker client
    ```shell    
    zenml container-registry register ecr_registry \
        --flavor=aws \
        --uri=$ECR_URI

    aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ECR_URI
    ```

- Register the metadata store:
    ```shell
    zenml metadata-store register rds_mysql \
        --flavor=mysql \
        --database=zenml \
        --secret=rds_authentication \
        --host=$RDS_MYSQL_ENDPOINT
    ```

- Register the secrets manager:
    ```shell
    zenml secrets-manager register aws_secrets_manager \
        --flavor=aws \
        --region_name=$REGION
    ```

- Configure your `kubectl` client and register the orchestrator:
    ```shell
    aws eks --region=$REGION update-kubeconfig --name=$EKS_CLUSTER_NAME
    kubectl create namespace zenml

    zenml orchestrator register eks_kubernetes_orchestrator \
        --flavor=kubernetes \
        --kubernetes_context=$(kubectl config current-context)
    ```

- Register the ZenML stack and activate it:
    ```shell
    zenml stack register kubernetes_stack \
        -o eks_kubernetes_orchestrator \
        -a s3_store \
        -m rds_mysql \
        -c ecr_registry \
        -x aws_secrets_manager \
        --set
    ```

- Register the secret for authenticating with your MySQL database:
    ```shell
    zenml secret register rds_authentication \
        --schema=mysql \
        --user=$RDS_MYSQL_USERNAME \
        --password=$RDS_MYSQL_PASSWORD
    ```

After all of this setup, you're now ready to run any ZenML pipeline on AWS!