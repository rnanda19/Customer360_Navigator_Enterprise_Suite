# CFPB <-> BANKING77 Taxonomy Mapping

Governs BP1 (Customer Intent Classification), BP2 (Friction Classification), BP4 (Journey Analytics), BP6 (GenAI Resolution Assistant) and BP8 (Executive Analytics) wherever the Master Plan calls for CFPB<->BANKING77 integration. Source data: `configs/taxonomy_mapping.yaml` (machine-readable version of this table).

## 1. Why this is a taxonomy crosswalk, not a row-level join

CFPB and BANKING77 share no common customer, account or transaction identifier, and the CFPB export delivered for this project (see `RAW_DATA_MANIFEST.md`) has no narrative-text column. There is therefore no way to join these two datasets row-by-row, and no way to jointly train a single text model on both. Per Master Plan Section 3/Section 7 (BP1), the integration is a **taxonomy/semantic mapping**: both datasets' category labels are mapped into a shared set of common banking-operation buckets so that BANKING77 (which has real customer-utterance text) can train/evaluate a text intent classifier, while CFPB's structured Product/Sub-product/Issue fields are mapped into the *same* bucket vocabulary for cross-dataset comparability in reporting (BP8) — never for claiming the two datasets describe the same customers or events.

## 2. Real, measured CFPB Product distribution

Measured directly from `data/raw/cfpb_complaints.csv` (1,048,575 data rows) on 2026-09-21 using `pandas.value_counts()` over the real file — not estimated.

| CFPB Product | Rows | % of file | In scope for BANKING77 overlap? |
|---|---|---|---|
| Credit reporting, credit repair services, or other personal consumer reports | 477,097 | 45.50% | No |
| Credit reporting or other personal consumer reports | 430,204 | 41.03% | No |
| Debt collection | 44,493 | 4.24% | No |
| Checking or savings account | 27,952 | 2.67% | Yes |
| Credit card or prepaid card | 25,486 | 2.43% | Yes |
| Mortgage | 12,133 | 1.16% | No |
| Money transfer, virtual currency, or money service | 8,263 | 0.79% | Yes |
| Vehicle loan or lease | 7,215 | 0.69% | No |
| Credit card | 6,575 | 0.63% | Yes |
| Student loan | 3,948 | 0.38% | No |
| Payday loan, title loan, or personal loan | 3,308 | 0.32% | No |
| Payday loan, title loan, personal loan, or advance loan | 1,187 | 0.11% | No |
| Prepaid card | 434 | 0.04% | Yes |
| Debt or credit management | 259 | 0.02% | No |
| Credit reporting | 21 | 0.00% | No |

**Finding: 6.55% of this CFPB file (68,710 of 1,048,575 rows) is in a Product category that has any plausible overlap with BANKING77's retail-banking-operations intents.** The remaining 93.45% (979,865 rows) — dominated by credit reporting (~86.5% of the whole file across its two product-name variants), debt collection, mortgage, vehicle loan, and student loan — describes complaint domains BANKING77 was never built to cover (BANKING77 is card/payment/transfer customer-service utterances from a single digital bank app). This is a real, measured property of the delivered file, not a modeling choice, and it should shape scope expectations for BP1/BP2/BP4/BP6/BP8: a taxonomy-mapped 'common banking operations' view is only defensible over a minority of this CFPB extract.

## 3. Common taxonomy buckets and their CFPB product candidates

| Bucket | CFPB product candidate(s) | CFPB sub-product candidate(s) | Confidence | Rationale |
|---|---|---|---|---|
| CARD_ISSUANCE_AND_LIFECYCLE | Credit card or prepaid card, Credit card, Prepaid card | General-purpose credit card or charge card, General-purpose prepaid card, Store credit card, Government benefit card | MEDIUM | BANKING77 categories about receiving/activating/losing/replacing a physical or virtual card map to CFPB's card-product family. CFPB does not separately code 'card lifecycle' as an Issue, so this is a product-level match only, not issue-level. |
| CARD_PAYMENT_ISSUES | Credit card or prepaid card, Credit card, Prepaid card | General-purpose credit card or charge card, General-purpose prepaid card | MEDIUM | Declined/failed/double-charged/fee-disputed card payments correspond to CFPB card-product complaints, but the specific CFPB Issue values for these rows have not yet been pulled and verified (Gate 2 follow-up) — confidence is capped at MEDIUM until that is done. |
| ATM_CASH_WITHDRAWAL | Checking or savings account, Credit card or prepaid card | Checking account, Savings account | LOW | CFPB does not have a dedicated ATM/cash-withdrawal product; ATM disputes are typically filed under the deposit-account product. This is an inference, not a confirmed CFPB coding rule — flagged LOW until cross-checked against real Issue values. |
| TRANSFERS | Money transfer, virtual currency, or money service, Checking or savings account | Domestic (US) money transfer, International money transfer | HIGH | CFPB's 'Money transfer, virtual currency, or money service' product is a direct, named match for BANKING77's transfer-related categories (sent/received/cancelled/declined/failed transfers, beneficiary and timing issues). |
| TOP_UP_AND_WALLET | Money transfer, virtual currency, or money service | Mobile or digital wallet, Virtual currency | LOW | BANKING77's 'top up' categories describe adding funds to a digital wallet/prepaid account, a product type CFPB does not code with the same granularity. Mapped to the closest available CFPB sub-product as a judgment call, not a confirmed equivalence. |
| FX_AND_EXCHANGE | Money transfer, virtual currency, or money service | International money transfer, Virtual currency | LOW | Exchange-rate and currency-support categories have no precise CFPB analog in this product list; mapped to the money-transfer/virtual-currency product as the nearest defensible match. |
| IDENTITY_AND_ACCOUNT_VERIFICATION | Checking or savings account, Credit card or prepaid card | Checking account, Savings account | LOW | Identity verification, PIN, and passcode categories could plausibly appear under deposit-account or card-product complaints in CFPB, but no CFPB Issue value confirming this has been pulled yet — treat as an open hypothesis, not a verified mapping. |
| FRAUD_AND_DISPUTES | Credit card or prepaid card, Checking or savings account | General-purpose credit card or charge card, Checking account | MEDIUM | Lost/stolen-card, compromised-card, refund, and duplicate-charge categories align with CFPB's well-known 'fraud or scam' / 'problem with a purchase' issue family under card and deposit products, though the exact Issue strings have not yet been verified against this file. |
| ACCOUNT_MANAGEMENT | Checking or savings account, Credit card or prepaid card | Checking account, Savings account | MEDIUM | Account closure and balance-after-deposit categories map to CFPB's deposit-account and card-account product families. |

Confidence is a stated judgment, not a computed score: **HIGH** means CFPB has a product literally named for this operation (transfers); **MEDIUM** means a plausible product-family match that has not yet been verified against real CFPB Issue-level values; **LOW** means the closest available CFPB product is a loose analog with no strong naming correspondence. Gate 2 follow-up work should pull the real Issue/Sub-issue value distribution (the same way Product/Sub-product were pulled here) before any MEDIUM/LOW bucket is used in a metric that gets reported externally.

## 4. Full BANKING77 category -> bucket assignment (all 77 categories)

| BANKING77 category | Bucket |
|---|---|
| `card_arrival` | CARD_ISSUANCE_AND_LIFECYCLE |
| `card_linking` | CARD_ISSUANCE_AND_LIFECYCLE |
| `exchange_rate` | FX_AND_EXCHANGE |
| `card_payment_wrong_exchange_rate` | CARD_PAYMENT_ISSUES |
| `extra_charge_on_statement` | CARD_PAYMENT_ISSUES |
| `pending_cash_withdrawal` | ATM_CASH_WITHDRAWAL |
| `fiat_currency_support` | FX_AND_EXCHANGE |
| `card_delivery_estimate` | CARD_ISSUANCE_AND_LIFECYCLE |
| `automatic_top_up` | TOP_UP_AND_WALLET |
| `card_not_working` | CARD_PAYMENT_ISSUES |
| `exchange_via_app` | FX_AND_EXCHANGE |
| `lost_or_stolen_card` | CARD_ISSUANCE_AND_LIFECYCLE |
| `age_limit` | IDENTITY_AND_ACCOUNT_VERIFICATION |
| `pin_blocked` | IDENTITY_AND_ACCOUNT_VERIFICATION |
| `contactless_not_working` | CARD_PAYMENT_ISSUES |
| `top_up_by_bank_transfer_charge` | TOP_UP_AND_WALLET |
| `pending_top_up` | TOP_UP_AND_WALLET |
| `cancel_transfer` | TRANSFERS |
| `top_up_limits` | TOP_UP_AND_WALLET |
| `wrong_amount_of_cash_received` | ATM_CASH_WITHDRAWAL |
| `card_payment_fee_charged` | CARD_PAYMENT_ISSUES |
| `transfer_not_received_by_recipient` | TRANSFERS |
| `supported_cards_and_currencies` | CARD_ISSUANCE_AND_LIFECYCLE |
| `getting_virtual_card` | CARD_ISSUANCE_AND_LIFECYCLE |
| `card_acceptance` | CARD_PAYMENT_ISSUES |
| `top_up_reverted` | TOP_UP_AND_WALLET |
| `balance_not_updated_after_cheque_or_cash_deposit` | ACCOUNT_MANAGEMENT |
| `card_payment_not_recognised` | CARD_PAYMENT_ISSUES |
| `edit_personal_details` | IDENTITY_AND_ACCOUNT_VERIFICATION |
| `why_verify_identity` | IDENTITY_AND_ACCOUNT_VERIFICATION |
| `unable_to_verify_identity` | IDENTITY_AND_ACCOUNT_VERIFICATION |
| `get_physical_card` | CARD_ISSUANCE_AND_LIFECYCLE |
| `visa_or_mastercard` | CARD_ISSUANCE_AND_LIFECYCLE |
| `topping_up_by_card` | TOP_UP_AND_WALLET |
| `disposable_card_limits` | CARD_ISSUANCE_AND_LIFECYCLE |
| `compromised_card` | FRAUD_AND_DISPUTES |
| `atm_support` | ATM_CASH_WITHDRAWAL |
| `direct_debit_payment_not_recognised` | TRANSFERS |
| `passcode_forgotten` | IDENTITY_AND_ACCOUNT_VERIFICATION |
| `declined_cash_withdrawal` | ATM_CASH_WITHDRAWAL |
| `pending_card_payment` | CARD_PAYMENT_ISSUES |
| `lost_or_stolen_phone` | FRAUD_AND_DISPUTES |
| `request_refund` | FRAUD_AND_DISPUTES |
| `declined_transfer` | TRANSFERS |
| `Refund_not_showing_up` | FRAUD_AND_DISPUTES |
| `declined_card_payment` | CARD_PAYMENT_ISSUES |
| `pending_transfer` | TRANSFERS |
| `terminate_account` | ACCOUNT_MANAGEMENT |
| `card_swallowed` | CARD_ISSUANCE_AND_LIFECYCLE |
| `transaction_charged_twice` | FRAUD_AND_DISPUTES |
| `verify_source_of_funds` | IDENTITY_AND_ACCOUNT_VERIFICATION |
| `transfer_timing` | TRANSFERS |
| `reverted_card_payment?` | CARD_PAYMENT_ISSUES |
| `change_pin` | IDENTITY_AND_ACCOUNT_VERIFICATION |
| `beneficiary_not_allowed` | TRANSFERS |
| `transfer_fee_charged` | TRANSFERS |
| `receiving_money` | TRANSFERS |
| `failed_transfer` | TRANSFERS |
| `transfer_into_account` | TRANSFERS |
| `verify_top_up` | TOP_UP_AND_WALLET |
| `getting_spare_card` | CARD_ISSUANCE_AND_LIFECYCLE |
| `top_up_by_cash_or_cheque` | TOP_UP_AND_WALLET |
| `order_physical_card` | CARD_ISSUANCE_AND_LIFECYCLE |
| `virtual_card_not_working` | CARD_PAYMENT_ISSUES |
| `wrong_exchange_rate_for_cash_withdrawal` | ATM_CASH_WITHDRAWAL |
| `get_disposable_virtual_card` | CARD_ISSUANCE_AND_LIFECYCLE |
| `top_up_failed` | TOP_UP_AND_WALLET |
| `balance_not_updated_after_bank_transfer` | ACCOUNT_MANAGEMENT |
| `cash_withdrawal_not_recognised` | ATM_CASH_WITHDRAWAL |
| `exchange_charge` | FX_AND_EXCHANGE |
| `top_up_by_card_charge` | TOP_UP_AND_WALLET |
| `activate_my_card` | CARD_ISSUANCE_AND_LIFECYCLE |
| `cash_withdrawal_charge` | ATM_CASH_WITHDRAWAL |
| `card_about_to_expire` | CARD_ISSUANCE_AND_LIFECYCLE |
| `apple_pay_or_google_pay` | CARD_PAYMENT_ISSUES |
| `verify_my_identity` | IDENTITY_AND_ACCOUNT_VERIFICATION |
| `country_support` | FX_AND_EXCHANGE |

## 5. Known gaps / next Gate 2 steps

- Real CFPB `Issue`/`Sub-issue` value distribution has not yet been pulled for the in-scope products — only `Product`/`Sub-product`. Several MEDIUM/LOW buckets above should be re-verified once that is done, and this document updated (never silently left stale).
- This mapping is unweighted by BANKING77 class frequency; whether the resulting bucket-level class balance is usable for a text classifier evaluated against it should be checked in the BP1 Gate 2/3 notebook, not assumed here.
- No row in this document was fabricated or estimated: every CFPB count is a real measurement; every bucket assignment is a disclosed judgment call subject to Gate 2 review.
