from django.http import JsonResponse
from django.forms.models import model_to_dict
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly, AllowAny


@api_view(["GET"])
@permission_classes((AllowAny,))
def userDetail(request, **kwargs):
    user = request.user
    payload = dict(
        id=None,
        email=None,
        username=None,
        game=None,
    )

    if not request.user.is_anonymous:
        userdict = model_to_dict(user)
        payload = dict(
            id=userdict["id"],
            email=userdict["email"],
            username=userdict["username"],
            game=None,
        )
        account = user.account
        accountdict = model_to_dict(account)
        payload["game"] = accountdict["game"]
        payload["deck"] = accountdict["deck"]

    return JsonResponse(payload)
