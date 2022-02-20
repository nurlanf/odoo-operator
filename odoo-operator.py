#!/usr/bin/env python3

import kopf
import kubernetes.config as k8s_config
import kubernetes.client as k8s_client
import requests
import pykube
import yaml


odoo_crd = k8s_client.V1CustomResourceDefinition(
    api_version="apiextensions.k8s.io/v1",
    kind="CustomResourceDefinition",
    metadata=k8s_client.V1ObjectMeta(name="odoos.operators.nurlanf.github.io"),
    spec=k8s_client.V1CustomResourceDefinitionSpec(
        group="operators.nurlanf.github.io",
        versions=[k8s_client.V1CustomResourceDefinitionVersion(
            name="v1",
            served=True,
            storage=True,
            schema=k8s_client.V1CustomResourceValidation(
                open_apiv3_schema=k8s_client.V1JSONSchemaProps(
                    type="object",
                    properties={
                        "spec": k8s_client.V1JSONSchemaProps(
                            type="object",
                            properties={
                                "version":  k8s_client.V1JSONSchemaProps(
                                type="string",
                                enum=["13.0","14.0","15.0"]
                            ),
                                "auto_backup":  k8s_client.V1JSONSchemaProps(
                                type="boolean"
                                )
                            }
                        ),
                        "status": k8s_client.V1JSONSchemaProps(
                            type="object",
                            x_kubernetes_preserve_unknown_fields=True
                        )
                    }
                )
            )
        )],
        scope="Namespaced",
        names=k8s_client.V1CustomResourceDefinitionNames(
            plural="odoos",
            singular="odoo",
            kind="Odoo",
            short_names=["od"]
        )
    )
)

try:
    k8s_config.load_kube_config()
except k8s_config.ConfigException:
    k8s_config.load_incluster_config()

api_instance = k8s_client.ApiextensionsV1Api()
try:
    api_instance.create_custom_resource_definition(odoo_crd)
except k8s_client.rest.ApiException as e:
    if e.status == 409:
        print("CRD already exists")
    else:
        raise e

def get_odoo_configmap_name(api, auto_backup=False):
    addons_path = f"/mnt/extra-addons"

    if auto_backup:
        addons_path += ",/mnt/default"

    doc = yaml.safe_load(f"""
        apiVersion: v1
        kind: ConfigMap
        data:
          odoo.conf: |
                [options]
                addons_path = {addons_path}
        """)

    kopf.adopt(doc)

    # Actually create an object by requesting the Kubernetes API.
    configmap = pykube.ConfigMap(api, doc)
    configmap.create()
    api.session.close()

    return configmap.metadata['name']


@kopf.on.create('operators.nurlanf.github.io', 'v1', 'odoos')
def create_odoo(namespace, spec, body, **kwargs):

    api = pykube.HTTPClient(pykube.KubeConfig.from_env())

    configmap = get_odoo_configmap_name(api, auto_backup=spec['auto_backup'])
    # Render the pod yaml with some spec fields used in the template.
    doc = yaml.safe_load(f"""
        apiVersion: v1
        kind: Pod
        spec:
          containers:
          - name: postgres
            image: postgres:11
            env:
            - name: POSTGRES_USER
              value: odoo
            - name: POSTGRES_PASSWORD
              value: odoo
            - name: POSTGRES_DB
              value: postgres
            - name: PGDATA
              value: "/var/lib/postgresql/data/postgres"
          - name: odoo
            image: odoo:{spec['version']}
            env:
            - name: HOST
              value: localhost
            - name: USER
              value: odoo
            - name: PASSWORD
              value: odoo
            volumeMounts:
            - name: odoo-conf
              mountPath: /etc/odoo/odoo.conf
              subPath: odoo.conf
          volumes:
          - name: odoo-conf
            configMap:
              name: {configmap}

    """)

    # Make it our child: assign the namespace, name, labels, owner references, etc.
    kopf.adopt(doc)

    pod = pykube.Pod(api, doc)
    pod.create()
    api.session.close()

    # Update the parent's status.
    return {'children': [pod.metadata['uid']]}

