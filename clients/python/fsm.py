class FSM:
    def __init__(self, initial_state = None):
        self.reset()
        if initial_state != None:
            self.state = initial_state

    def reset(self):
        self.state = None
        self.input = None
        self.transitions = dict()
    
    def process(self, input):
        self.input = input
        action, next = self.getTransition(self.input, self.state)
        if action != None:
       	    action(self)
        self.state = next
    
    def getTransition(self, input, state):
        try: return self.transitions[(input, state)]
        except: pass
        try: return self.transitions[(None, state)]
        except: pass
        try: return self.transitons[(input, None)] 
        except: pass
        try: return self.transitions[(None, None)]
        except: raise Exception("No matching transitions found.")

    def addTransition(self, input, state, action, next):
        self.transitions[(input, state)] = (action, next)

    def addTransitionList(self, input_list, state, action, next):
        for input in input_list:
            self.addTransition(input, state, action, next)

    def addTransitionAnyInput(self, state, action, next):
        self.transitions[(None, state)] = (action, next) 
    
    def addTransitionAnyState(self, input, action, next):
        self.transitions[(input, None)] = (action, next) 

    def addDefaultTransition(self, action = None, next = None):
        self.transitions[(None, None)] = (action, next)

