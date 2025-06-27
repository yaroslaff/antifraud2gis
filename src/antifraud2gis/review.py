from typing import Optional

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, Text, Float, Integer, ForeignKey

import datetime
from rich import print_json

from .user import User
from .company import Company
from .base import Base


class Review(Base):

    __tablename__ = "review"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("user.public_id", ondelete="CASCADE"), index=True, nullable=False)
    object_id: Mapped[str] = mapped_column(ForeignKey("company.object_id", ondelete="CASCADE"), index=True, nullable=False)
    provider: Mapped[str] = mapped_column(Text)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)

    user: Mapped[User] = relationship(back_populates="reviews")
    company: Mapped[Company] = relationship(back_populates="reviews")

    # _user: 'User'

    def __init__( self,
        id: str,
        user: Optional[User] = None,
        user_id: Optional[str] = None,
        company: Optional[Company] = None,
        object_id: Optional[str] = None,
        provider: str = "",
        rating: Optional[float] = None,
    ):
        self.id = id
        self.provider = provider
        self.rating = rating
        
        # Handle user assignment
        if user is not None:
            self.user = user
            self.user_id = user.public_id
        elif user_id is not None:
            self.user_id = user_id
        else:
            raise ValueError("Either user object or user_id must be provided")
            
        # Handle company assignment
        if company is not None:
            self.company = company
            self.object_id = company.object_id
        elif object_id is not None:
            self.object_id = object_id
        else:
            raise ValueError("Either company object or company_id must be provided")


    def __old_init__(self, data, user=None, company=None):
        # data is either from our local db or from 2gis company
        from .company import Company

        self._data = data
        

        # self.review_id = data['id']
        self.rating = data['rating']
        self.object_id = data.get('oid') or data['object']['id']
        self.uid = data.get('uid') or data['user']['public_id']
        self.user_name = data.get('user_name') or data['user']['name']
        self.text = data.get('text')
        self.provider = data.get('provider')

        self._user = None
        self._company = company
        self.user_age = None

        date = data.get('date_created') or data['created']

        if 'T' in date:
            self.created = datetime.datetime.strptime(date.split('.')[0], "%Y-%m-%dT%H:%M:%S")
        else:
            self.created = datetime.datetime.strptime(date, "%Y-%m-%d")
        # self.created = datetime.datetime.strptime(data['date_created'].split('T')[0], "%Y-%m-%d")

        # age from today (grows every time)
        self.age = (datetime.datetime.now() - self.created).days

        

        if user:
            self.set_user(user)
        

        self.title, self.address = Company.resolve_oid(self.object_id)

    def set_user(self, user):
        self._user = user
        if self._user.birthday():
            # set only for public profile
            self.user_age = (self.created - self._user.birthday()).days


    @property
    def created_str(self):
        return self.created.strftime("%Y-%m-%d")

    @property    
    def get_user(self) -> 'User': 
        if not self._user:
            from .user import User, get_user
            user = get_user(self.uid)
            self.set_user(user)

        return self._user

    @property
    def user_url(self):
        return f'https://2gis.ru/x/user/{self.uid}'


    def is_empty(self):
        if self.uid is None:
            return True

        self.user.load()
        if self.user.nreviews() <= 1:            
            return True
        
        return False

    def get_town(self) -> str: 
        if self.address is None:
            return None
        return self.address.split(',')[0].replace(u'\xa0', u' ')


    def __repr__(self):
        # print_json(data=self._data)
        from .user import User

        return f'Review({self.provider} {self.user} {self.rating} > {self.company})'