#!/bin/bash
docker-compose run --rm backend ./manage.py shell -c "
from django.contrib.auth.models import User;
from piplayer.models import Account

if User.objects.filter(username='root'):
    root = User.objects.get(username='root');
    root.set_password('root');
    root.save();
else:
    root = User.objects.create_superuser('root', 'root@dev.cruxle.org', 'root')
root_account, created = Account.objects.get_or_create(user=root)
root_account.save()

if User.objects.filter(username='al'):
    al = User.objects.get(username='al');
    al.set_password('al');
    al.save();
else:
    al = User(username='al', email='al@dev.cruxle.org', password='al')
    al.save()
al_account, created = Account.objects.get_or_create(user=al)
al_account.save()
"
