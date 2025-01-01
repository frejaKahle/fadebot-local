import json, os
from threading import Lock
from typing import TypeVar, Callable, Any

T = TypeVar('T')

class SharedResource:
    def __init__(self, resource: T):
        self.__res: T = resource
        self.lock: Lock = Lock()
    def get(self) -> T:
        with self.lock: return self.__res
    def set(self, resource: T):
        with self.lock: self.__res = resource
    def call(self,func: Callable, **kwargs) -> Any:
        with self.lock:
            result = func(self.__res,**kwargs)
        return result

class SharedConfig(SharedResource):
    def __init__(self, location: str):
        self.location = location
        self.__file = open(location)
        self.__res: dict
        try: d = json.load(self.__file)
        except: d = {}
        super().__init__(d)
    def __rewrite(self):
        self.__file.truncate()
        json.dump(self.__res, self.__file)
    def call(self,func: Callable, **kwargs) -> Any:
        with self.lock:
            result = func(self.__res,**kwargs)
            self.__rewrite()
        return result
    def set(self, resource: dict):
        with self.lock:
            self.__res = resource
            self.__rewrite()
    def update(self,*args,**kwargs):
        with self.lock:
            self.__res.update(*args,**kwargs)
            self.__rewrite()            

aio_cfg = SharedConfig(os.path.abspath("config\\audioplayer.json"))
bot_cfg = SharedConfig(os.path.abspath("config\\bot.json"))