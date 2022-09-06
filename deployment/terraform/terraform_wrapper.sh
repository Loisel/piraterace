#!/bin/bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
TF_DIRECTORY=$SCRIPT_DIR/bin
TF_VERSION="1.2.8"

if [ ! -d $TF_DIRECTORY ]; then
  mkdir -p $TF_DIRECTORY
  cd $TF_DIRECTORY
  wget https://releases.hashicorp.com/terraform/${TF_VERSION}/terraform_${TF_VERSION}_linux_amd64.zip
  unzip terraform_${TF_VERSION}_linux_amd64.zip
  chmod +x terraform
  ln -s terraform terraform-${TF_VERSION}
fi

$TF_DIRECTORY/terraform "$@"