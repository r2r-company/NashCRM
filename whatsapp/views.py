# whatsapp/views.py
from wsgiref import headers

import requests
from django.template.defaulttags import url
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import WhatsAppMessage
from .serializers import WhatsAppMessageSerializer


class WhatsAppReceiveMessage(APIView):
    def post(self, request):
        serializer = WhatsAppMessageSerializer(data={
            **request.data,
            "direction": "in"
        })
        if serializer.is_valid():
            serializer.save()
            return Response({"status": "received", "data": serializer.data})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class WhatsAppSendMessage(APIView):
    def post(self, request):
        serializer = WhatsAppMessageSerializer(data={
            **request.data,
            "direction": "out"
        })
        if serializer.is_valid():
            # тут буде виклик до стороннього API
            serializer.save()
            return Response({"status": "sent (not really, just mocked)", "data": serializer.data})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)




class WhatsAppCloudSendView(APIView):
    def post(self, request):
        url = "https://graph.facebook.com/v22.0/665703413295307/messages"
        token = "EAAOMzDQcZAEEBO7NI6ONBX9FHg0pvU5BZC50yGem66MrlxSTyfNmxxZB8OqfMtKEALmsdqrjCijpg54mY4oZB9iSSbkojFV9PD0MZCPkMREJxVCM69t0jsY9X0wPhb8KjK7yFuMmxeDlNVT2SpCkLP69NUmcPVwF48doZBbvm6v52mPEumeCQ4McFTF77IywJLpdVnYKoE3O1ZAAffjbzMd2UQpDCB7cUqr2fUZD"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        payload = {
            "messaging_product": "whatsapp",
            "to": "380997777777",  # або request.data.get("to")
            "type": "template",
            "template": {
                "name": "r2r_company",
                "language": {
                    "code": "uk_UA"
                }
            }
        }

        res = requests.post(url, json=payload, headers=headers)
        return Response(res.json(), status=res.status_code)