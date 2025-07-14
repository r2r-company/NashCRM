from django.shortcuts import render

# Create your views here.
from rest_framework.views import APIView
from rest_framework.response import Response

from asterisk.models import SIPAccount


class SIPConfigView(APIView):
    def get(self, request):
        account = SIPAccount.objects.get(user=request.user)
        return Response({
            "sip_uri": f"sip:{account.sip_username}@{account.domain}",
            "password": account.sip_password,
            "ws_url": account.ws_url
        })