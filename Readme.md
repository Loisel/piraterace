=== Setup backend
```
docker-compose build backend
maint/migrate.sh
maint/init_superuser.sh
docker-compose up backend
```

=== Setup Frontend
```
docker-compose build frontend
maint/run_npm_install.sh
docker-compose up frontend
```
