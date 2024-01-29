import os
import kopf
import kubernetes
import yaml
import jinja2

@kopf.on.create('targetworkloads')
def create_fn(name, namespace, body, logger, **kwargs):

    targetLabels = list(body['target']['labels'])

    path = os.path.join(os.path.dirname(__file__), 'templates/configmap.yaml')
    template_content = open(path, 'rt').read()
    
    template = jinja2.Template(template_content)
    text = template.render(labels=targetLabels)
    
    manifest = yaml.safe_load(text)

    logger.info(f"ConfigMap is created: \n{manifest}")
