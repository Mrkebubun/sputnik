

def wrapper(func):
    def fun(self):
        print 'barkbarkbark'
        print self.name
        func(self)
    return fun
        

class test:
    def __init__(self):
        self.name = 'big bear'


    @wrapper
    def fun(self):
        print 'mewmewmew'


a = test()

a.fun()
