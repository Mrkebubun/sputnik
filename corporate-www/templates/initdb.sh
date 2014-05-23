#!/bin/bash

database init
contracts add BTC
contracts add {{currency}}

contracts add BTC/{{currency}}

contracts set BTC contract_type cash
contracts set BTC denominator 100000000
contracts set BTC hot_wallet_limit 1000000000
contracts set BTC cold_wallet_address {{cold_wallet_address}}

contracts set {{currency}} contract_type cash
contracts set {{currency}} denominator 10000
contracts set {{currency}} description {{description}}
contracts set {{currency}} deposit_instructions {{deposit_instructions}}

contracts set BTC/{{currency}} contract_type cash_pair
contracts set BTC/{{currency}} tick_size 100
contracts set BTC/{{currency}} lot_size 1000000
contracts set BTC/{{currency}} denominator 1
contracts set BTC/{{currency}} denominated_contract_ticker {{currency}}
contracts set BTC/{{currency}} payout_contract_ticker BTC

permissions add Default
EOF

cat << EOF | $profile_root/tools/leo
accounts add customer
accounts add m2
accounts add remainder

accounts add onlinecash
accounts set onlinecash type Asset

accounts add offlinecash
accounts set offlinecash type Asset

accounts add depositoverflow
accounts set depositoverflow type Liability

accounts add pendingwithdrawal
accounts set pendingwithdrawal type Liability

accounts add adjustments
accounts set adjustments type Asset

admin add admin
EOF
