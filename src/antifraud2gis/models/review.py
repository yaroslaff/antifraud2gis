from typing import Optional

from sqlalchemy.orm import Session, Mapped, mapped_column, relationship
from sqlalchemy import String, Text, Float, Integer, DateTime, ForeignKey, Boolean, select, exists

from datetime import datetime, timezone
from rich import print_json

from .author import Author
from .company import Company
from ..base import Base
from ..db import DBSession
from ..settings import settings

class Review(Base):

    __tablename__ = "review"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    # user_id could be null if external review
    author_id: Mapped[str] = mapped_column(ForeignKey("author.public_id", ondelete="CASCADE"), index=True, nullable=True)
    object_id: Mapped[str] = mapped_column(ForeignKey("company.object_id", ondelete="CASCADE"), index=True, nullable=False)
    # user name
    _name: Mapped[str] = mapped_column(Text, nullable=True)
    provider: Mapped[str] = mapped_column(Text)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    author: Mapped[Author] = relationship(back_populates="reviews")
    company: Mapped[Company] = relationship(back_populates="reviews")

    # if review is deleted on 2gis
    deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")


    # _user: 'User'

    def __old_init1__( self,
        id: str,
        user: Optional[Author] = None,
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
            self.author_id = user.public_id
        elif user_id is not None:
            self.author_id = user_id
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
        self.author_age = None

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

    def UNUSED_set_user(self, user):
        self._user = user
        if self._user.birthday():
            # set only for public profile
            self.author_age = (self.created - self._user.birthday()).days


    @classmethod
    def exists(cls, review_id: str, dbsession: Session) -> bool:
        stmt = select(exists().where(cls.id == review_id))
        return bool(dbsession.scalar(stmt))


    @property
    def name(self) -> str:
        if self._name is not None:
            return f'{self.provider}:{self._name}'
        else:
            return self.author.name

    @property
    def age(self) -> int:
        created = self.created
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)

        return (datetime.now(timezone.utc) - created).days

    @property
    def author_age(self) -> int | None:
        """ author.age from registration """
        if self.author is None:
            return None

        return self.user.birthday() - self.created

    @property
    def author_age_1r(self) -> int | None:
        """ author.age from 1st review"""
        if self.author is None:
            return None
        return (self.created - self.author.first_review()).days


    @property
    def created_str(self):
        return self.created.strftime("%Y-%m-%d")

    @property    
    def get_user(self) -> 'Author': 
        if not self._user:
            from .user import Author, get_user
            user = get_user(self.uid)
            self.set_user(user)

        return self._user

    @property
    def user_url(self):
        return f'https://2gis.ru/x/user/{self.uid}'


    def is_empty(self):
        if self.author_id is None:
            return True

        with DBSession() as dbsession:
            if self.author.nreviews() <= 1:
                return True
        
        return False

    def get_town(self) -> str: 
        if self.address is None:
            return None
        return self.address.split(',')[0].replace(u'\xa0', u' ')


    def as_dict(self) -> dict:

        rdata = dict(
            id=self.id,
            author_id=self.author_id,
            private=self.author.private if self.author else None,
            author_created=None,
            object_id=self.object_id,
            name=self.name,
            provider=self.provider,
            rating=self.rating,
            
            # created: when review was written (in 2gis)
            created=self.created.strftime("%Y-%m-%d %H:%M:%S"),
            # author_age: how old was autho
            author_age=(self.created - self.author.created).days if self.author else None,                        
            review_age = (datetime.now() - self.created).days
        )
        if self.provider == "2gis" and self.author:
            rdata['author_created'] = self.author.created.strftime("%Y-%m-%d %H:%M:%S")
        else:
            rdata['author_created'] = None

        return rdata

    @classmethod
    def exists_in_db(cls, review_id: str, dbsession: Session) -> bool:
        #stmt = select(exists().where(Review.id == self.id))

        #n = dbsession.query(func.count(Review.id))\
        #        .filter(Review.id == review_data['id'])\
        #        .scalar()


        # check if review is already in db
        stmt = select(exists().where(Review.id == review_id))
        return bool(dbsession.scalar(stmt))

    def is_fresh(self, max_age_days: int | None = None) -> bool:

        # def: settings.max_review_age
        if max_age_days is None:
            
            max_age_days = settings.max_review_age

        # make comparison ignoring possible timezone issues
        created = self.created
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)            

        age_days = (datetime.now(timezone.utc) - created).days
        return age_days <= max_age_days

    def __repr__(self):
        # print_json(data=self._data)
        from .author import Author

        return f'Review({self.id} {self.created.date()} {self.provider} {self.author} {self.rating} > {self.company})'