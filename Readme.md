### Setup backend
```
docker-compose build backend
maint/migrate.sh
maint/init_superuser.sh
docker-compose up backend
```

### Setup Frontend
```
docker-compose build frontend
maint/run_npm_install.sh
docker-compose up frontend
```

### Start Nginx

```
docker-compose up nginx
```

## Server Deployment

### Terraform

cd deployment/terraform/piraterace
../terraform_wrapper.sh init
../terraform_wrapper.sh apply

### Ansible

cd deployment/ansible
ansible-playbook -i hosts playbooks/piraterace-dev.yaml