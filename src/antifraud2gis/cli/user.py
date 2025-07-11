import argparse

from ..models.company import CompanyList, Company
from ..models.user import Author

def add_user_parser(subparsers):

    user_parser = subparsers.add_parser("user", help="info/operations about users")
    user_parser.add_argument("cmd", choices=['info', 'company' , 'reviews'])
    user_parser.add_argument("uid")

    return user_parser


def handle_user(args: argparse.Namespace):
    cmd = args.cmd
    cl = CompanyList()
    u = Author(args.uid)
    cmd = args.cmd

    if cmd == "info":
        print(u)
    elif cmd == "company":
        ci = u.get_company_info(args.args[0])
        print_json(data=ci)
    elif cmd == "reviews":
        for r in u.reviews():
            print(r)
    else:
        print("Unknown command", cmd)

