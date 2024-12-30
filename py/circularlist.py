import asyncio
from copy import deepcopy
from typing import Union, Callable, Any, TypeVar
from collections.abc import Iterable
from readerwriterlock import rwlock
from sys import getsizeof
from types import SimpleNamespace

REOC = SimpleNamespace()
REOC.WAIT = 0
REOC.SDEF = 1

T = TypeVar('T')

# These class provide a circular linked list buffer for use in audio buffering for fadebot discord audio streaming
# Each node is a rather simple memory structure containing its data and the link to the next node
class CircularNode():
    def __init__(self, data: T = None, next_node = None) -> None:
        self.data : T = data
        self.nxt : CircularNode = next_node
        lock = rwlock.RWLockFair()
        self.read_lock = lock.gen_rlock
        self.write_lock = lock.gen_wlock
class CircularList():
    def __init__(self, con_data: Union[Iterable[T], tuple[T,int], int] = None):
        '''Generates a circular list from the provided object. See insert_new_nodes for how the list is generated.'''
        self.read_ptr: CircularNode[T] = None                           # The current read position (next read call will read THIS NODE)
        self.write_ptr: CircularNode[T] = None                          # The current write position (next write call will read THE FOLLOWING NODE)
        self.length = 0                                                 # Used to track length, accessable threadsafely via len()  

        lock = rwlock.RWLockFair()                                      # threading lock for this list
        self.read_lock = lock.gen_rlock                                 # read lock (multiple readers can read at once, but not during writes)
        self.write_lock = lock.gen_wlock                                # write lock (exclusive lock)

        self.write_threads_waiting: list[asyncio.Event] = []
        self.read_threads_waiting: list[asyncio.Event] = []
        self.read_adv_pending: asyncio.Task | None = None
        self.write_adv_pending: asyncio.Task | None = None

        self.insert_new_nodes(construction_data=con_data)               # generate the starting list

    def __iter__(self): return self
    def __next__(self) -> T: return self.read()   
    def __getitem__(self, index: int) -> CircularNode: return self.read_index(idx=index)
         
    def __len__(self):                                                  # used to get length of the list
        '''threadsafely returns the length of the list'''
        with self.read_lock():                                            
            return self.length       

    def index_from(self, node : CircularNode, idx : int) -> CircularNode:           
        '''threadsafe index function based from the provided node position'''   
        with self.read_lock():
            true_idx = idx % self.length                                # find the index (number of times to go to next node)
            for _ in range(true_idx):                                   # loop through true_idx times
                with node.read_lock():                                  # obtain cnode's lock (r)
                    node = node.nxt                                     # go to the next node
            return node                                                 # return the node
    
    def index_from_tus(self, node : CircularNode, idx : int) -> CircularNode:
        '''index function based from the current read position, WARNING: not threadsafe'''
        true_idx = idx % self.length                                    # find the true index requested
        if not true_idx: return node                                    # if index is 0 return that node
        return self.read_index_tus(true_idx - 1, node.nxt)              # else find the next node and return that with a decremented index search
           
    def read_index(self, idx : int) -> CircularNode:
        '''threadsafe index function based from the current read position'''
        return self.index_from(self.read_ptr,idx)
    def write_index(self, idx : int) -> CircularNode:
        '''threadsafe index function based from the current write position'''
        return self.index_from(self.write_ptr,idx)
        
    def read_index_tus(self, idx : int) -> CircularNode:
        '''index function based from the current read position, WARNING: not threadsafe'''
        return self.index_from_tus(self.read_ptr,idx)
    def write_index_tus(self, idx : int) -> CircularNode:
        '''index function based from the current write position, WARNING: not threadsafe'''
        return self.index_from_tus(self.write_ptr,idx)

    def wait_for_read(self) -> None:
        '''Used in funtions that write to signal when node writing can happen without overwriting of data.'''
        self.pend_read_ptr()
        self.pend_write_ptr()
        with self.read_lock():
            if (self.read_threads_waiting or
                self.write_ptr.nxt != self.read_ptr): return
        wait_event = asyncio.Event()
        with self.write_lock():
            self.write_threads_waiting.append(wait_event)
        asyncio.get_event_loop().run_until_complete(wait_event.wait())
        del self.write_threads_waiting[0]

    def wait_for_write(self) -> None:
        '''Used in funtions that read to signal when node reading can happen without reoccurrence of data.'''
        self.pend_read_ptr()
        self.pend_write_ptr()
        with self.read_lock():
            if (self.read_threads_waiting or
                self.write_ptr != self.read_ptr): return
        wait_event = asyncio.Event()
        with self.write_lock():
            self.read_threads_waiting.append(wait_event)
        asyncio.get_event_loop().run_until_complete(wait_event.wait())
        del self.read_threads_waiting[0]

    def allow_read(self) -> None:
        with self.write_lock():
            if self.read_threads_waiting:
                self.read_threads_waiting[0].set()
    def allow_write(self) -> None:
        with self.write_lock():
            if self.write_threads_waiting:
                self.write_threads_waiting[0].set()
    
    def insert_new_nodes(self, construction_data: Union[Iterable[T], tuple[T,int], int] = None, left_node: CircularNode = None) -> int:
        '''Inserts a new set of nodes into the list following left_node, which defaults to current_write, with optional starting data. The behavior of the function changes depending on what type of data is supplied.
        :Union construction_data: the data used to fill the new node(s)
        :CircularNode left_node: The CircularNode instance that the new nodes will be appended after
        Iterable: Each new node is generated in order directly from the iterable. Note: the provided iterator must be reversable.
        tuple[object,int]: Creates a number of new nodes specified by the integer, each new node is generated as a deep copy of the object.
        int: Creates a number of nodes specified by the integer, each new node is generated with no data.
        All other cases: the construction data passed in is added singularly to the node , as if [construction_data] had been passed instead of construction_data.
        Returns the number of new nodes inserted.'''
        # NOTE: if you are using this function and you want to place an Iterable,
        #   a Tuple(object(),int), or an int into a singular Node, escape it by
        #   placing it into a single element list:
        #   ex_list.insert_new_nodes(iterable_data) --> ex_list.insert_new_nodes([iterable_data]
        it = None                                                       # iterable that will be filled using construction data
        match construction_data:                                        # this match statement converts construction_data into an iterable
                    case Iterable():                                    # if it's already an iterable:
                        if not construction_data: return 0              #   stop if it's empty
                        it = construction_data                          #   otherwise, use it as is
                    case tuple(object(),int()):                         # if it is a tuple of anything and an integer:
                        if construction_data[1] < 1: return 0           #   stop if the integer is non-positive
                        it = [deepcopy(construction_data[0])            #   otherwise, create a list of repeating data copies of the anything
                              for i in range(construction_data[1])]     #   a number of times equal to the integer
                    case int():                                         # if it is an integer:
                        if construction_data < 1: return 0              #   stop if the integer is non-positive
                        it = [None for i in range(construction_data)]   #   otherwise, create a list of Nones of length equal to the integer
                    case _:                                             # if it is anything else:
                        it = [construction_data]                        #   place it into a single element list

        with   (self.write_lock()):                                     # acquire lock for: list (w)
            if no_nodes := (not self.write_ptr):                        # if the list had no nodes, set a value and:
                self.write_ptr = CircularNode()                         #   make current_write a new node
                self.write_ptr.nxt = self.write_ptr                     #   set up it's next node to be itself
                self.read_ptr = self.write_ptr                          #   initialize current read pointer

            if not left_node:   
                left_node = self.write_ptr                              # default left_node to current_write   
            first_node = left_node                                      # save the node before the insertion for later

            with   (left_node.write_lock()):                            # acquire lock for left_node (w)
                count = self.length                                     # setup a variable to keep track of how many nodes were added
                right_node = left_node.nxt                              # find the node to the right of the insertion
                for item in it:                                         # loop through the iterable generated from construction_data
                    left_node.nxt = CircularNode(data = item)           #   create a new
                    left_node = left_node.nxt                           #   moves to the new node
                    self.length += 1                                    #   increments the length counter
                left_node.nxt = right_node                              # set the final node's next node to the node to the rught of the insertion 
                count = self.length - count                             # calculate the actual count of nodes added to the list

                
        if (right_node == self.read_ptr and                             # if the node to the right was the read node ...
            any([ i != None for i in it])):                             # and the data inserted was not empty:
            self.read_ptr = first_node.nxt                              #  move the current read pointer to the beginning of the insertion
            self.allow_read()
        if (first_node == self.write_ptr):
            self.allow_write()
        if no_nodes: self.delete_after(left_node)                       # delete the dummy node created for an empty list
        return count                                                    # return the number of added nodes

    def prepend_new_nodes(self, construction_data: Union[Iterable[T], tuple[T,int], int] = None) -> int:
        '''Inserts new nodes directly before the current write node. Useful if you want to avoid overwriting the inserted data.'''
        return self.insert_new_nodes(construction_data,self.write_index(-1))
    
    def insert_before_read(self, construction_data: Union[Iterable[T], tuple[T,int], int] = None) -> int:
        '''Inserts new nodes directly before the current read node. Usefull if you want to avoid overwriting the inserted data and for having immediate access to it.'''
        return self.insert_new_nodes(construction_data,self.read_index(-1))

    def delete_after(self,left_node: CircularNode) -> bool:
        '''Deletes the node to the right of the specified node. 
        Return value is True if deletion was successful, otherwise False.'''
        if len(self) <= 1 or not left_node: return False                # dissallow deletion if no input or there are only 1 or 0 nodes in the list
        with   (self.read_lock() and left_node.write_lock() and         #   and the node to the left (rw)
                left_node.nxt.write_lock()):                            #   and the node to be deleted (w)
            to_delete = left_node.nxt                                   # designate the node to be deleted

            if self.read_ptr == to_delete:                              # This code block moves the read and write pointers 
                self.adv_read_ptr(to_delete.nxt)                        # ...
            if self.write_ptr == to_delete:                             # ...
                self.adv_write_ptr(left_node)                           # .

            del to_delete                                               # delete the freed node
            self.length -= 1                                            # remove 1 from length count

            return True                                                 # returns True if the node was successfully deleted, locks are released

    def delete_node(self,node_to_delete : CircularNode) -> bool:
        '''Deletes the node to the right of the specified node. Significantly slower than delete_after in long lists
        Return value is True if deletion was successful, otherwise False.'''
        return self.delete_after(self.index_from(node_to_delete,-1))    # delete after the previous node
    
    def pend_write_ptr(self) -> None:
        if self.write_adv_pending and not self.write_adv_pending.done():
            asyncio.get_event_loop().run_until_complete(
                self.write_adv_pending)
    def adv_write_ptr(self, node: CircularNode) -> None:
        self.pend_write_ptr()
        def awp():
            with self.write_lock():
                self.write_ptr = node
        self.write_adv_pending = asyncio.create_task(awp())

    def overwrite(self,data = None, unblock = True) -> int:
        '''writes to the list without care for if data might be getting overwritten'''
        with   (self.read_lock() and                                    # acquire locks for: the list (r),
                self.write_ptr.write_lock()):                           #   the write node (w)
            self.write_ptr.data = data                                  # write the data, locks are released
            size = getsizeof(self.write_ptr.data)
        with   (self.write_lock()):                                     # acquire list locks (rw)
            self.write_ptr = self.write_ptr.nxt                         # move to the next node, locks released
        self.allow_read()
        return size

    def write(self, data = None) -> int:
        '''writes to the list, ensuring no data gets overwritten before it gets read'''
        self.wait_for_read()
        return self.overwrite()
    
    def pend_read_ptr(self) -> None:
        if self.read_adv_pending and not self.read_adv_pending.done():
            asyncio.get_event_loop().run_until_complete(
                self.read_adv_pending)
            
    def adv_read_ptr(self, node: CircularNode) -> None:
        self.pend_read_ptr()
        def arp(): 
            with self.write_lock(): self.read_ptr = node
        self.read_adv_pending = asyncio.create_task(arp())

    def read_regardless(self, unblock=True) -> T:
        '''reads data from the current read node regaless of any data reoccurrence, then moves read_ptr to the next node'''
        self.pend_read_ptr()
        with   (self.read_lock() and self.read_ptr.read_lock()):        # acquire node lock (r)
            data = self.read_ptr.data                                   # retrieve data, release lock
        self.adv_read_ptr(self.read_ptr.nxt)                            # advance the read pointer
        if unblock and self.write_threads_waiting:                      # if the function is set to unblock writes:
            self.allow_write()                                          #   allow writing to happen if it caught up, release lock
        return data                                                     # return the read data

    def read(self, reoccurrence_behavior = REOC.WAIT, default_data: T = None) -> T:
        '''Reads data from the current read node, avoiding reoccurrences, then moves read_ptr node to the next node.'''
        data = default_data
        if reoccurrence_behavior:
            with   (self.read_lock()):
                if self.read_ptr == self.write_ptr:
                    return data
        else:
            self.wait_for_write()
            return self.read_regardless()

    def pop(self) -> T:
        '''Reads data from the current read node, then deletes that node, moving the read node pointer to the next node in the process.'''
        with self.read_lock(): to_delete = self.read_ptr
        self.wait_for_write()
        self.delete_node(to_delete)
        return self.read_regardless(False)