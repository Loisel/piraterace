# PirateRace

PirateRace is a turn based multiplayer 2D tile game with a nasty random fate component. You compete with other pirates for the gold treasure your great great grand-father has hidden on a remote island. Plan your next moves and trash your opponents. But beware, fate might strike any time to ruin your carefully planned treasure hunt.

## Technologies

- Backend: Python, Django
- Frontend: Ionic + Angular + Phaser
- Hosting: Nginx
- Deployment: Terraform, Ansible, docker-compose

## Developer Setup

### Initialize Containers

```
docker-compose pull
docker-compose build
maint/migrate.sh
maint/init_superuser.sh
docker-compose up backend
```

### Start all components

```
docker-compose down
maint/backend_collectstatic.sh
maint/backend_migrate.sh
maint/frontend_npm_install.sh
docker-compose up -d
```

### Open the game

The game is running under the nginx which forwards all calls to the correct backends.

http://localhost:1337

## Cloud Deployment

The game is hosted on hetzner cloud ( https://www.hetzner.com/cloud ) with the following environments:

- (WORK IN PROGRESS) dev.piraterace.com : Development Environment
- (TODO LATER) piraterace.com : Production Environment

It consists of 1 vserver per environment which contains the full stack (database, backend, frontend, etc.). If this setup does not satisfy the requirements any more we can always scale out.

### Overview

#### Technologies

* Terraform ( https://www.terraform.io/ ) is an infrastructure as code tool that lets you create cloud servers and other resources via a configuration language.
* Ansible ( https://www.ansible.com/ ) Ansible is a configuration management software which works with yaml-files to setup a certain server state.

#### Infrastructure as code

* `deployment/terraform` : contains the terraform modules (currently just 1 module, called piraterace) and the terraform_wrapper.sh (automatically downloads the correct terraform version if nonexistant)
* `deployment/ansible` : contains ansible playbooks, configuration and hosts files

### Terraform

Check out the repository which contains this README here on any machine with internet access (e.g. your laptop) and run the following commands. The commands are all idempotent, you can run them as often as you want to ensure the cloud state matches the configuration. The terraform_wrapper.sh script will download the correct terraform version, if it has not been downloaded already (works on Linux x86_64). Otherwise you can install terraform yourself and use it directly.

```
# Switch to the correct terraform module
cd deployment/terraform/piraterace

# Initialize terraform plugins, etc. -> it is safe to run this command everytime, but it is only needed to be run once or if plugins change, terraform will prompt you if the command needs to be run 
../terraform_wrapper.sh init

# Check what changes need to be performed and then apply those changes. If no changes need to be performed the configuration already matches the state in the cloud.
../terraform_wrapper.sh apply
```

### Ansible

Ansible configures servers to match a certain desired state. The commands are idempotent, you can run them as often as you like to ensure the state matches the configuration of the yaml files. Run them from a machine with internet access (e.g. your laptop).

The playbook will install docker and docker-compose, setup let's encrypt and will start piraterace.

(currently only the installation of docker + docker-compose is implemented)

```
# Install the ansible binary
sudo apt install ansible

cd deployment/ansible
ansible-playbook -i hosts playbooks/piraterace-dev.yaml
```
