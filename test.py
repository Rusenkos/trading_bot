import os

from tinkoff.invest import Client

TOKEN = "t.L_Dsrj7_NulOKVi1xd-jVWbKxcg0pkHfCqGzrtVjcpV0SmDl40p1OJ9EEa-CZpX_QMIYxFG17qOdjdGyw24CIA"


def main():
    with Client(TOKEN) as client:
        r = client.instruments.find_instrument(query="BBG001M2SC01")
        for i in r.instruments:
            print(i)


if __name__ == "__main__":
    main()