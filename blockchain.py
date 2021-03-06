import functools #for reduce
from utility.hash_util import hash_block #My library for hashing 
import json #to serialise for storage
from block import Block 
from transaction import Transaction
from utility.verification import Verification #verification helper class
from wallet import Wallet
import requests #for http requests to share data between nodes

# reward for mining a single block given to the miner
MINING_REWARD = 10

class Blockchain:
    def __init__(self, hosting_node_id, node_id):
        #first block of the chain stored as an object
        genesis_block =  Block(0, '', [], 100, 0)
        #Initialising empty blockchain list
        self.__chain = [genesis_block]
        #list of open transactions  
        self.__open_transactions = []
        #loads data from file
        self.node_id = node_id
        self.hosting_node = hosting_node_id
        self.__peer_nodes = set()
        self.resolve_conflicts = False
        self.load_data()


    def get_chain(self):
        return self.__chain[:]

    def get_open_transactions(self):
        return self.__open_transactions[:]

    def load_data(self):
        try:
            #read blockchain from file
            with open('blockchain.txt-{}'.format(self.node_id), mode='r') as f:
                    file_content = f.readlines()
                    blockchain = json.loads(file_content[0][:-1])
                    updated_blockchain = []
                    for block in blockchain: #Loop through the string to put in data structure
                        converted_tx = [Transaction(tx['sender'], tx['recipient'], tx['signature'], tx['amount']) for tx in block['transactions']]
                        updated_block = Block(block['index'], block['previous_hash'], converted_tx, block['proof'], block['timestamp'])
                        updated_blockchain.append(updated_block)
                    self.__chain = updated_blockchain #set chain to dictionary above
                    open_transactions = json.loads(file_content[1][:-1])
                    updated_transactions = [] #load transactions similarly
                    for tx in open_transactions:
                        updated_transaction = Transaction(tx['sender'], tx['recipient'], tx['signature'], tx['amount'])
                        updated_transactions.append(updated_transaction)
                    self.__open_transactions = updated_transactions
                    peer_nodes = json.loads(file_content[2])
                    self.__peer_nodes = set(peer_nodes)
        except (FileNotFoundError, IndexError):
            print("File created")
                  

    def save_data(self):
        try:
            with open('blockchain.txt-{}'.format(self.node_id), mode='w') as f:
                    #from ordereddict to dict for json serialise
                    saveable_chain = [block.__dict__ for block in [Block(block_el.index, block_el.previous_hash, [tx.__dict__ for tx in block_el.transactions], block_el.proof, block_el.timestamp) for block_el in self.__chain]]
                    f.write(json.dumps(saveable_chain)) #write chain to file
                    f.write('\n')
                    saveable_tx = [tx.__dict__ for tx in self.__open_transactions] #from ordereddict to dict for json serialise
                    f.write(json.dumps(saveable_tx)) #write open transations to file
                    f.write('\n')
                    f.write(json.dumps(list(self.__peer_nodes))) #stores peer nodes
        except IOError:
            print("Saving failed.") #if lack of permissions etc.


    def proof_of_work(self): #carry out POW
        last_block = self.__chain[-1]
        last_hash = hash_block(last_block)
        proof = 0
        while not Verification.valid_POW(self.__open_transactions, last_hash, proof): #loop till valid pow found
            proof +=1
        return proof


    # get the balance of a user based on transaction history
    #uses lambda expressions
    def get_balance(self, sender=None):
        if sender == None:
            if self.hosting_node == None:
                return None
            participant = self.hosting_node
        else: 
            participant = sender

        tx_sender = [[tx.amount for tx in block.transactions
                    if tx.sender == participant] for block in self.__chain]
        open_tx_sender = [tx.amount
                        for tx in self.__open_transactions if tx.sender == participant]
        tx_sender.append(open_tx_sender)
        amount_sent = functools.reduce(lambda tx_sum, tx_amt: tx_sum + sum(tx_amt) if len(tx_amt) > 0 else tx_sum + 0, tx_sender, 0)
        tx_receiver = [[tx.amount for tx in block.transactions
                        if tx.recipient == participant] for block in self.__chain]
        amount_received = functools.reduce(lambda tx_sum, tx_amt: tx_sum + sum(tx_amt) if len(tx_amt) > 0 else tx_sum + 0, tx_receiver, 0)
        return amount_received - amount_sent

    # return last transaction amount 
    def get_last_transaction_amount(self):
        """Returns the last value of the current blockchain without popping"""
        if len(self.__chain) > 0:
            return self.__chain[-1]
        else:
            return 0

    # function to add transaction to blockchain
    def add_transaction(self, recipient, sender, signature, amount=1.0, is_receiving=False):
        """ Add a transaction to a blockchain
        Return: whether transaction was successful
        Arguments:
            :sender: The sender of the coins
            :receiver: The receiver of the coins
            :amount: The value of the transaction, default is 1
        """
        #if self.hosting_node == None:
        #    return False
        #transaction stored as a object
        transaction = Transaction(sender, recipient, signature, amount)
        #verify transaction can be made before adding to open_transactions
        if Verification.verify_transaction(transaction, self.get_balance):
            self.__open_transactions.append(transaction)
            self.save_data()
            if not is_receiving: #only broadcast to peer node if on the first node doing the transaction.
                for node in self.__peer_nodes:
                    url = 'http://{}/broadcast-transaction'.format(node)
                    try:
                        response = requests.post(url, json={'sender': sender, 'recipient': recipient, 'amount': amount, 'signature':signature})
                        if response.status_code == 400 or response.status_code == 500:
                            print('Transaction declined, needs resolving')
                            return False  
                    except requests.exceptions.ConnectionError:
                        continue
            return True
        return False
        

    # mine block and produce mining rewars as well as verifying transactions
    def mine_block(self):
        if self.hosting_node == None:
            return None
        last_block = self.__chain[-1]
        hashed_block = hash_block(last_block)
        proof = self.proof_of_work()
        #transaction for mining the block added when block is mined
        reward_transaction = Transaction('MINING', self.hosting_node, '', MINING_REWARD)
        #copied so that the mining transaction only completes if the block is mined successfully
        copied_transactions = self.__open_transactions[:] #verify all but the mining transaction
        for tx in copied_transactions:
            if not Wallet.verify_transaction(tx):
                return None
        copied_transactions.append(reward_transaction) #reward tx for the block
        block = Block(len(self.__chain), hashed_block, copied_transactions, proof)
        
        #block added to chain therefore mined
        self.__chain.append(block) #add block to the chain
        self.__open_transactions = [] #clear open transactions
        self.save_data() #save the new chain
        for node in self.__peer_nodes:
            url = 'http://{}/broadcast-block'.format(node)
            converted_block = block.__dict__.copy()
            converted_block['transactions'] = [tx.__dict__ for tx in converted_block['transactions']]
            try:
                response = requests.post(url, json = {'block': converted_block})
                if response.status_code == 400 or response.status_code == 500:
                    print('Block declined, needs resolving')
                if response.status_code == 409:
                    self.resolve_conflicts = True

            except requests.exceptions.ConnectionError:
                continue
        return block

    
    #to update from other nodes' blockchains
    def add_block(self, block):
        transactions = [Transaction(tx['sender'], tx['recipient'], tx['signature'], tx['amount']) for tx in block['transactions']]
        proof_is_valid = Verification.valid_POW(transactions[:-1], block['previous_hash'], block['proof'])
        hashes_match = hash_block(self.__chain[-1]) == block['previous_hash']
        if not proof_is_valid or not hashes_match:
            return False
        converted_block = Block(block['index'], block['previous_hash'], transactions, block['proof'], block['timestamp'])
        self.__chain.append(converted_block)
        stored_transactions = self.__open_transactions[:]
        for itx in block['transactions']:
            for opentx in stored_transactions:
                if opentx.sender == itx['sender'] and opentx.recipient == itx['recipient'] and opentx.amount == itx['amount'] and opentx.signature == itx['signature']:
                    try:
                        self.__open_transactions.remove(opentx)
                    except ValueError:
                        print('item was already removed')
        self.save_data()
        return True


    def resolve(self):
        #Method to resolve conflicts (greatest valid chain wins)
        winner_chain = self.__chain
        replace = False
        for node in self.__peer_nodes:
            url = 'http://{}/chain'.format(node)
            try:
                response = requests.get(url)
                node_chain = response.json()
                node_chain = [Block(block['index'], block['previous_hash'], [Transaction(tx['sender'], tx['recipient'],tx['signature'], tx['amount']) for tx in block['transactions']], block['proof'], block['timestamp']) for block in node_chain]
                node_chain_length = len(node_chain)
                local_chain_length = len(winner_chain)
                if node_chain_length > local_chain_length and Verification.chain_verification(node_chain):
                    winner_chain = node_chain
                    replace = True
            except requests.exceptions.ConnectionError:
                continue
        self.resolve_conflicts = False
        self.__chain = winner_chain
        if replace:
            self.__open_transactions = []
        self.save_data()
        return replace


    def add_peer_node(self, node):
        #adds a new node to peer node set
        self.__peer_nodes.add(node)
        self.save_data()

    def remove_peer_node(self, node):
        #removes a node to peer node set if it exists
        self.__peer_nodes.discard(node)
        self.save_data()

    def get_peer_nodes(self):
        #returns a list of connected nodes
        return list(self.__peer_nodes)[:]