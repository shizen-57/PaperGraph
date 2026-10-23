# Joint Client Selection and Resource Allocation for Federated Learning

## Abstract

We jointly optimize client selection and resource allocation for federated learning over heterogeneous devices.

## 1 Introduction

Existing approaches select clients primarily based on data volume and availability. They ignore whether the update arrives on time.

## 2 Method

Our scheduler scores each client by expected contribution and bandwidth, selecting 10 clients per round.

| method | accuracy |
|---|---|
| FedAvg | 71.2 |
| Ours | 78.4 |

## 3 Limitations

We assume clients never drop out during a round.
