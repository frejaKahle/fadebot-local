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
        if not os.path.exists(location):
            if os.path.exists("_internal\\" + location):
                self.__file = open("_internal\\" + location,"r+")
            else:
                with open(location, 'w') as file:
                    file.write("{}")
                self.__file = open(location, "r+")
        else:
            self.__file = open(location, "r+")
        d: dict
        try: d = json.load(self.__file)
        except: d = {}
        super().__init__(d)
    def __rewrite(self):
        d = self.get()
        with self.lock:
            self.__file.truncate(0)
            self.__file.seek(0)
            json.dump(d, self.__file, skipkeys=False, ensure_ascii=True, check_circular=True, allow_nan=True, cls=None, indent=None, separators=None)
            self.__file.seek(0)
    def call(self,func: Callable, **kwargs) -> Any:
        with self.lock:
            result = func(super().__res,**kwargs)
            self.__rewrite()
        return result
    def set(self, resource: dict):
        self.set(resource)
        self.__rewrite()
    def update(self,*args,**kwargs):
        self.get().update(*args,**kwargs)
        self.__rewrite()

aio_cfg = SharedConfig("config\\audioplayer.json")
bot_cfg = SharedConfig("config\\bot.json")