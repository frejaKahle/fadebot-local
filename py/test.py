from typing import Callable

class c1():
    def __init__(self, time: float) -> None:
        self.time = time
    def default_time(self)-> float: return self.time

class c2():
    def __init__(self, time: Callable[[],float]) -> None:
        self.time: Callable[[],float] = time
class c3():
    def __init__(self, time: Callable[[],float]) -> None:
        self.time: Callable[[],float] = lambda: time() * 2.0

a = c1(2.0)
b = c2(a.default_time)
c = c3(b.time)
print (a.time,a.default_time(),c.time())
a.time = 4.0
print (a.time,a.default_time(),c.time())
b.time = lambda: 3.0
print (a.time,a.default_time(),c.time())