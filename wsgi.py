from app import app

def handler(event, context):
    return app(event, context)
