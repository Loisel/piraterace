from rest_framework.request import Request
from django.utils.functional import SimpleLazyObject
from django.contrib.auth.middleware import get_user


class AuthenticationMiddlewareJWT(object):
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.user = SimpleLazyObject(lambda: self.__class__.get_jwt_user(request))
        return self.get_response(request)

    @staticmethod
    def get_jwt_user(request):
        from rest_framework_simplejwt.authentication import JWTAuthentication

        user = get_user(request)
        if user.is_authenticated:
            return user
        try:
            user_jwt = JWTAuthentication().authenticate(Request(request))
            if user_jwt is not None:
                # print(f"jwt user: {user_jwt}")
                return user_jwt[0]
        except Exception as e:
            print(e)
            pass
        return user  # AnonymousUser
