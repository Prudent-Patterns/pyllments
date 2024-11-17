from fastapi import FastAPI
import param

from pyllments.base.model_base import Model


class APIModel(Model):
    app = param.ClassSelector(default=FastAPI(), class_=FastAPI, instantiate=False)
    routes_dict = param.Dict(default={})
    
    def __init__(self, **params):
        super().__init__(**params)

    def create_post_route(self, route_name, route_function):
        pass

