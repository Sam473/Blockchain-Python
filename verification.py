from hash_util import hash_block, hash_string_256 #My library for hashing 

class Verification:
    # Validates the blockchain to ensure that it hasn't been manipulated
    @classmethod
    def chain_verification(cls, blockchain):
        #enumerate() returns a tuple with indexes and data from blockchain list
        for (index, block) in enumerate(blockchain):
            if index == 0:
                continue
            if block.previous_hash != hash_block(blockchain[index-1]):
                return False
            if not cls.valid_POW(block.transactions[:-1], block.previous_hash, block.proof): 
                print('Proof of work is invalid')
                return False
        return True


    # function to verify whether transaction can be completed based on the sender's balance
    @staticmethod
    def verify_transaction(transaction, get_balance):
        sender_balance = get_balance()
        return sender_balance >= transaction.amount


    #Check whether a hash is valid, nonce is number only used once
    @staticmethod
    def valid_POW(transactions, last_hash, nonce):
        guess = (str([tx.to_ordered_dict() for tx in transactions]) + str(last_hash) + str(nonce)).encode()
        guess_hash = hash_string_256(guess)
        return guess_hash[0:2] == '00'


    @classmethod
    def verify_transactions(cls, open_transactions, get_balance):
        #Verifies all open transactions
        return all([cls.verify_transaction(tx, get_balance()) for tx in open_transactions])