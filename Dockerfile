FROM python:3.8-alpine
RUN apk --update add gcc build-base
RUN pip install --no-cache-dir kopf kubernetes requests pykube-ng pyyaml
ADD odoo-operator.py /
CMD kopf run /odoo-operator.py