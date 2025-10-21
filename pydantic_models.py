import re
import datetime
from typing import List, Optional, Annotated, Literal, Dict, Any, Self, Tuple
from enum import Enum
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_ai import Agent, RunContext

class CategoryEnum(str, Enum):
    ELECTRONICS = 'electronics'
    FASHION = 'fashion'
    BOOKS = 'books'
    HOME_APPLIANCES = 'home_appliances'
    OTHERS = 'others'

# class FilterTypeEnum(str, Enum):
#     RANGE = 'range'
#     MULTISELECT = 'multiselect'
#     SINGLESELECT = 'singleselect'
#     BOOLEAN = 'boolean'

# class FilterValue(BaseModel):
#     type: FilterTypeEnum
#     selection: Optional[List[str]]
#     range: Optional[Tuple[Optional[float], Optional[float]]]
#
# class UserFilter(BaseModel):
#     name: str 
#     value: FilterValue

class UserFilter(BaseModel):
    name: str
    type: Literal['range', 'multiselect', 'singleselect', 'boolean']
    selection: Optional[List[str]] = None
    range: Optional[Tuple[Optional[float], Optional[float]]] = None

class ProductReview(BaseModel):
    """Product Review & perception from other users"""
    ratings: Annotated[float, Field(le=5.0, ge=0.0)] = 0.0
    num_ratings: int = -1
    num_reviews : int = -1

    @field_validator('ratings', mode='before')
    @classmethod
    def val_ratings(cls, x: float | None) -> float:
        if not x:
            return 0.0
        return x

    @field_validator('num_ratings', mode='before')
    @classmethod
    def val_num_ratings(cls, x: str | int) -> int:
        if not x:
            return -1
        if isinstance(x, str):
            return int(x.replace(',', ''))
        return x 

    @field_validator('num_reviews', mode='before')
    @classmethod
    def val_num_reviews(cls, x: str | int) -> int:
        if not x:
            return -1
        if isinstance(x, str):
            return int(x.replace(',', ''))
        return x 

class ProductClass(BaseModel):
    """Category/type of the product desired by the user"""
    category: Annotated[CategoryEnum, Field(description="The category of the product")] = CategoryEnum.OTHERS
    type: Annotated[str, Field(description="The type of product within the category")] = ''

class Product(BaseModel): 
    """Product Specifications"""
    id: Optional[str] = None
    pro_class : Annotated[Optional[ProductClass] ,Field(description="The category/type of the product")] = None
    price: int 
    name: str
    url: str
    image: Optional[str] 
    review: Optional[ProductReview] 
    details: List[str]
    delivery_date: datetime.date | str | None = None

    @field_validator('price', mode='before')
    @classmethod
    def val_price(cls, x: str | int) -> int:
        if isinstance(x, str):
            return int(re.sub(r'[^\d]', '', x))
            # return int(x.replace(',', ''))
        return x 

class SearchSpecs(BaseModel):
    """Required details for searching the product on the site"""
    pro_class : Annotated[ProductClass ,Field(description="The category/type of the product")] = ProductClass()
    query: Annotated[str, Field(description="The user's query for the product")] = ''
    site: Annotated[str, Field(description="The best website to search for the product")] = ''
    site_filters: Annotated[Optional[List[UserFilter]], Field(description="A list of filters available on the site")] = None
    filtered_site_filters: Annotated[Optional[List[UserFilter]], Field(description="A list of filters relevant to the user")] = None
    user_filters: Annotated[Optional[List[UserFilter]], Field(description="A list of filters to apply when searching for the product")] = None

class ShopResult(BaseModel):
    """Final Result of the shopping agent"""
    products: List[Product] = Field(description="A list of products matching the user's query")
    recommended: Product = Field(description="The best product matching the user's query")
    message: Optional[str] = Field(description="A message indicating if no products were found")
    flow: List[str] = []
    steps: int = 0

# class SearchResult(BaseModel):
#     """Final Result of the shopping agent"""
#     products: Annotated[List[Product] ,Field(description="A list of products matching the user's query")]
#     best_site: Annotated[str, Field(description="Most suitable web site for shopping the required product")] = ''
#     site_filters: Annotated[Optional[List[UserFilter]], Field(description="A list of filters available on the site")] = None
#     message: Annotated[Optional[str], Field(description="A message indicating if no products were found")] = 'No products found !'

# class SearchDeps(BaseModel):
#     """Dependencies for the base shopping agent"""
#     search_specs : SearchSpecs
#     og_query: str 
#     query : str 
#     best_site: str

class ShopDeps(BaseModel):
    """Dependencies for the base shopping agent"""
    og_query: str = ''
    query : str 
    # search_deps : SearchDeps
    llm: Any 
    model_id: str 
    search_specs : SearchSpecs 
    # modelConfig: dict = Field(default_factory=lambda: {"temperature":0.2, "max_output_tokens":1024})
    modelConfig: Optional[Dict] = None
    candidates : Annotated[Optional[List[Product]], Field(description="A list of candidate products")] = None
    flow: List[str] = []
    steps: int = 0
    # playwright states
    context_man : Any = None
    playwright: Any = None
    browser: Any = None
    context: Any = None
    page: Any = None 


    @model_validator(mode='after')
    def val_query(self: Self) -> Self:
        if not self.query:
            self.query = self.og_query
        return self

