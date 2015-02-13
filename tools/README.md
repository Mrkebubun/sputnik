### create_backup_keychain

Used to create your backup keychain for the Sputnik Bitgo/MultiSignature integration support.
In order to run, you need `bitgo.py` from

```
git clone https://github.com/MimeticMarkets/bitgo
```

You'll also need pycrypto 2.7a1, pycoin, and sjcl:

```
sudo apt-get install python-pip
sudo pip install pycoin
sudo pip install sjcl
wget https://ftp.dlitz.net/pub/dlitz/crypto/pycrypto/pycrypto-2.7a1.tar.gz
tar xfz pycrypto-2.7a1.tar.gz
cd pycrypto-2.7a1
sudo python setup.py install
```

Then simply run:

```
python create_backup_keychain.py prod
```

Use the output of that program in the sputnik administrator to configure your multisig wallet.

Remember to store the output in a safe and secure location.

