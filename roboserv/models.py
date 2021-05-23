from django.db import models

# Create your models here.
import datetime

from django.db import models
from django.utils import timezone
from django.contrib import admin

import random



movements = {
    "u": "move one field forward",
    "l": "turn left",
    "r": "turn right",
    "t": "turn around",
    "b": "move one field back",
    "f": "move two fields forward",
    "s": "move three fields forward",
}


class Game(models.Model):
    
    
    def deal(self):
        
        for player in self.player_set.all():
            
            liste = []
            
            
            for i in range(10):
                        
                # random number
                n = random.randint(0,6)
                
                # random card out of movements
                card = list(movements.keys())[n]
                
                # append in list till 10 cards for 
                liste.append(card)
                
            
                
            player.cards = "".join(liste)
            player.save()
            

class Player(models.Model):

    game = models.ForeignKey(Game, on_delete=models.CASCADE)
    
    name = models.CharField(max_length=200)
    
    moves = models.CharField(max_length=5, blank=True)
    
    cards = models.CharField(max_length=10, blank=True)
    
    def __str__(self):
        return self.name
    
