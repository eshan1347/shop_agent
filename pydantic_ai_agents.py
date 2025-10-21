import asyncio
import pydantic
from types import NoneType
from typing import List, Optional, Annotated, Literal, Dict, Any, Self, Tuple
# from google import genai # type: ignore
from pydantic_ai import Agent, RunContext, UsageLimits
from site_scraper import get_filters, get_filtered_products, get_products, playwright_enter, playwright_exit
from pydantic_models import Product, ProductClass, ProductReview, UserFilter, ShopResult, ShopDeps, SearchSpecs
from dotenv import load_dotenv
import json
import logging
import sys
from fastapi import FastAPI, WebSocket

load_dotenv('./.env')
logging.basicConfig(stream=sys.stderr, level=logging.INFO)
logger = logging.getLogger(__name__)

MODEL_ID = 'google-gla:gemini-2.5-flash-lite'
MAX_RETRIES = 3

class Chatbot:

    class CoachChatbot:
        def __init__(self):
            self.ws  = None
            self._prompt_waiters: dict[str, tuple[asyncio.Event, dict]] = {}
            # self.userResponseEvent = None
            # self.userResp = None

        def set_ws(self, ws: WebSocket):
            self.ws = ws

        async def prompt_user(self, prompt: str, prompt_id: Optional[str] = None, timeout: Optional[float] = None) -> Optional[str]:
            if not prompt_id:
                prompt_id = str(id(prompt) + int(asyncio.get_event_loop().time()*1000))
            event = asyncio.Event()
            self._prompt_waiters[prompt_id] = (event, {'response': None})
            # self.userResponseEvent = asyncio.Event()
            # async def ws_prompt(prompt: str) -> None:
            if self.ws: 
                logger.info('WS present !')
                await self.ws.send_json({
                    'type': 'prompt',
                    'prompt_id': prompt_id,
                    'question': prompt
                })
            else:
                logger.info('No WS :(') 
            try:
                if timeout:
                    await asyncio.wait_for(event.wait(), timeout)
                else:
                    await event.wait()
            except asyncio.TimeoutError:
                logger.error(f'Request Timed out :(')
                del self._prompt_waiters[prompt_id]
                return None
            _, data = self._prompt_waiters.pop(prompt_id)
            return data.get('response')
            # await ws_prompt(prompt)
            # self.userResp = None
            # return await self._wait4resp()

        # async def _wait4resp(self):
        #     await self.userResponseEvent.wait()
        #     return self.userResp
        
        def set_userResp(self, userResp: str, prompt_id: Optional[str] = None) -> bool:
            if prompt_id and prompt_id in self._prompt_waiters:
                event, data = self._prompt_waiters[prompt_id]
                data['response'] = userResp
                event.set()
                return True
            logger.error(f'No matching prompt waiter for response: {prompt_id}')
            return False
            # self.userResp = userResp
            # if self.userResponseEvent:
            #     self.userResponseEvent.set()

    model_id: str 
    max_retries: int
    usage_limits: UsageLimits
    shop_agent: Agent[ShopDeps, ShopResult]
    gen_agent: Agent[None, str]
    context_man : Any = None
    playwright: Any = None
    browser: Any = None
    context: Any = None
    page: Any = None 
    coach: CoachChatbot

    def __init__(self, model_id: str = MODEL_ID, max_retries: int = MAX_RETRIES, top_k: int = 10, ws: Optional[WebSocket] = None):
        self.model_id = model_id
        self.max_retries = max_retries
        self.usage_limits = UsageLimits(request_limit=20, total_tokens_limit=25000)
        self.coach = self.CoachChatbot()
        self.coach.set_ws(ws)

        self.shop_agent = Agent[ShopDeps, ShopResult](
            model=MODEL_ID,
            output_type=ShopResult,
            deps_type=ShopDeps,
            retries=MAX_RETRIES, 
        )

        self.gen_agent = Agent[NoneType, str](
            model=MODEL_ID,
            output_type=str,
            deps_type=NoneType,
            retries=MAX_RETRIES, 
        )
    
        @self.shop_agent.system_prompt
        def sys_prompt0():
            return """
            You are a shopping agent specialising in helping users find the most suitable product. 
            Use the following tools to assist you in your task:
            - get_pro_class: Extract the product category & type from the user's query.
            - prompt_user0: Prompt the user for further details about the product.
            - rephrase_query : Generate a very concise product search query - combining original query & user provided details
            - get_best_site: Find the best website to search for the product.
            - get_site_filters: Retrieve all the available filters on the best site for the product.
            - trim_site_filters: Filter out & get only the relevant & user demanded filters for the site.
            - prompt_user1: Prompt the user for further details about the product using the available filters
            - get_candidates : Return the best candidates found for the product 

            You may use prompt_user0, rephrase_query & prompt_user1 tool calls more than once as needed but use the rest of the tools only once. 
            Example workflow: 
            user query -> get_pro_class(user_query) -> prompt_user0(product_class) -> rephrase_query(query) -> get_best_site(product_class) -> get_site_filters(product_class, best_site) -> trim_site_filters(site_filters)-> prompt_user1(filtered_site_filters, product_class) -> get_candidates(user_filters, search_query) -> final answer
            """

        @self.gen_agent.system_prompt
        def sys_prompt1() -> str:
            return """
            You are general question answering agent . Follow the given user's instruction religiously !
            """
        @self.shop_agent.tool
        async def get_pro_class(context: RunContext[ShopDeps]) -> None:
            """
            Get the product type & category from the user's query
            - Use to retrieve the product category & type from the user's query
            """
            # logger.info(f'node get_pro_class , deps: {context.deps}')
            context.deps.steps += 1
            query = context.deps.query
            res = await self.gen_agent.run(
                user_prompt= f"""You are an agent specialising in identifying a products class, type & category. 
                Return output in the specified pydantic base model format. Input Query: {query}""",
                usage = context.usage,
                usage_limits = self.usage_limits,
                output_type=ProductClass
            )
            context.deps.search_specs.pro_class = res.output
            # print(f'Pro class: {context.deps.search_specs.pro_class}')
            # print(f'Model: {context.model}')
            step = f'Step {context.deps.steps}: get_pro_class -> {context.deps.search_specs.pro_class}'
            context.deps.flow.append(step)
            logger.info(step)
            # return context.deps.search_specs.pro_class

        @self.shop_agent.tool
        async def rephrase_query(context: RunContext[ShopDeps]) -> None:
            """
            Rephrase the user query for more better & efficient searching . 
            Combine original user prompt along with the additional details provided by the user to create a single coherant query.
            - Use if the query is too short or vague 
            - Use if user has provided new information
            """
            # logger.info(f'node rephrase_query , deps: {context.deps}')
            context.deps.steps += 1
            query = context.deps.query
            res = await self.gen_agent.run(
                user_prompt=f"""
                Rephrase the original query & the provided details : {query}.
                Simple return the rephrased query. 
                The result should be short & include all of the necessary keywords.
                You can discard irrelevant details for a more concise query . 
                Keep in mind this query will be used for searching products for the users !
                Remove all punctuation & keeo the query less than 7 words
                """
            )
            context.deps.query = res.output
            step = f'Step {context.deps.steps}: rephrase_query -> {query} => {res.output}'
            context.deps.flow.append(step)
            logger.info(step)
            # return res.output

        @self.shop_agent.tool 
        async def prompt_user0(context: RunContext[ShopDeps]) -> None:
            """Prompt the user for further details about the product
            - Use to get details from the user about their ideal & needed product.
            - Useful for generating a more specific search query.
            - Useful for understanding how to filter products better.
              """
            context.deps.steps += 1
            query = context.deps.query
            pro_class = context.deps.search_specs.pro_class
            res = await self.gen_agent.run(
                user_prompt=f"""
            Prompt user to get more details about the particular product they wish to purchase - their specifications, qualities
            Tune your questions based on the product type & category
            - Use to generate a prompt to the users that answers all the relevant questions needed to search for the ideal product
            Product Class : {pro_class}
            User query: {query} 
            """,
                deps=None,
                usage=context.usage,
                usage_limits=self.usage_limits
            )
            user_prompt = res.output
            # logger.info(f'node prompt_user0 , deps: {context.deps}')
            # qE = input(user_prompt + "\nAnswer: ")
            qE = await self.coach.prompt_user(user_prompt)
            if qE:
                context.deps.query += ' ' + qE
            else:
                raise
            step = f'Step {context.deps.steps}: prompt_user0 -> {context.deps.query}'
            context.deps.flow.append(step)
            logger.info(step)
            # return qE

        @self.shop_agent.tool
        async def get_best_site(context: RunContext[ShopDeps]) -> None:
            """Get the best & most suitable website for searching the users product"""
            # logger.info(f'node get_best_site , deps: {context.deps}')
            context.deps.steps += 1
            pro_class = context.deps.search_specs.pro_class
            # best_site = await search_agent.run(f"Find the best website to search for {pro_class.category} of type {pro_class.type}. Just return the domain name without any prefixes or suffixes.", usage=context.usage, deps=context.deps.search_deps)
            best_site = 'https://www.flipkart.com'
            context.deps.search_specs.site = best_site
            step = f'Step {context.deps.steps}: get_best_site -> {best_site}'
            context.deps.flow.append(step)
            logger.info(step)
            # return best_site

        @self.shop_agent.tool
        async def get_site_filters(context: RunContext[ShopDeps]) -> None:
            """Retrieve all the available filters on the best site for the product
            - Use to retrieve all the available filters for the product on the site 
            - This can then be later used to retrieve user preferences for filtering the products
            """
            # logger.info(f'node get_site_filters , deps: {context.deps}')
            context.deps.steps += 1
            context.deps.context_man, context.deps.playwright, context.deps.browser, context.deps.context, context.deps.page = await playwright_enter()
            # filters = await search_agent.run(f"Retrieve all the filters available on {context.deps.search_specs.site}", usage=context.usage, deps=context.deps.search_deps)
            context.deps.search_specs.site_filters = await get_filters(context.deps.page, context.deps.search_specs.site, context.deps.query)
            step = f'Step {context.deps.steps}: get_site_filters -> {len(context.deps.search_specs.site_filters) if context.deps.search_specs.site_filters else 0}'
            context.deps.flow.append(step)
            logger.info(step + f'\n{context.deps.search_specs.site_filters}')
            # return context.deps.search_specs.site_filters

        @self.shop_agent.tool
        async def trim_site_filters(context: RunContext[ShopDeps]) -> None:
            context.deps.steps += 1
            filtered_site_filters = await self.gen_agent.run(
            user_prompt=f"""
            You are an specialised agent that takes in a list of UserFilters[name, type, selection, range] & 
            returns a list of UserFilter only containing relevant filters based on their attributes & the user query. 
            EXCLUDE Filters that only have 1 option in their selection !
            EXCLUDE Filters whose values users has already given in {context.deps.query} !
            Using user query, additional information provided by the user & the product - select the most important filters
            
            Filters availble: {context.deps.search_specs.site_filters}
            Input User Query: {context.deps.og_query}
            User specified product features: {context.deps.query} 
            """,
            usage = context.usage,
            usage_limits = self.usage_limits,
            output_type=List[UserFilter])

            context.deps.search_specs.filtered_site_filters = filtered_site_filters.output
            step = f'Step {context.deps.steps}: trim_site_filters {len(context.deps.search_specs.site_filters)} -> {len(filtered_site_filters.output) if filtered_site_filters.output else 0}'
            context.deps.flow.append(step)
            logger.info(step + f'\nTrimmed User filters: \n{filtered_site_filters.output}')

        @self.shop_agent.tool 
        async def prompt_user1(context: RunContext[ShopDeps]) -> None:
            """Prompt the user for how to apply filters 
            - Using the previously fetched site filters available - get exact user preferences on how to filter the products
            - Store these user filters in a structured form such that these can be applied while searching for products
            """
            # logger.info(f'node prompt_user1 , deps: {context.deps}')
            context.deps.steps += 1
            filters = context.deps.search_specs.filtered_site_filters if context.deps.search_specs.filtered_site_filters else context.deps.search_specs.site_filters
            if filters:
                res = ''
                for filter in filters:
                    user_prompt = f" describe how {filter} should be used: \nleave blank to skip !"
                    # res += f'Filter: {filter}, Answer:{input(user_prompt + "Answer: ")}\n'
                    ans = (await self.coach.prompt_user(user_prompt)).strip()
                    if ans and ans != '.':
                        res += f'Filter: {filter}, Answer:{ans}\n'
                list_user_filter_schema = pydantic.TypeAdapter(List[UserFilter]).json_schema()
                # logger.info(f'User Filter response:{res}\nlist_user_filter_schema: {list_user_filter_schema}')
                user_filters = await self.gen_agent.run(
                    user_prompt=f"""
                    You are an specialised agent that takes in different user preferences & filters for a product - compiles & captures the user intent &
                    return output in the specified pydantic base model format.
                    The Filters are listed one by one with the format => Filter: name type all_possible values Answer: User answer 
                    STRICTLY , IF THE USER GIVES NO ANSWER FOR A FILTER - COMPLETELY SKIP THAT FILTER !!!
                    Pay special attention to the text after Answer: & select the appropriate choices from the selection or range given at the start for each filter.
                    
                    EXAMPLE:
                    Input :
                    Filter: name='CLOCK SPEED' type='multiselect' selection=['1.5 - 1.9 GHz', '2 - 2.5 GHz', '2.2 - 2.4 GHz', '2.5 GHz Above', 'Below 1.5 GHz', 'Less than 900 MHz'] range=None, Answer: 1 
                    Explanation : For the above Filter , the user has given their preferred value - match it with the appropriate present value & return the result . If no values match - skip the particular filter
                    Output: UserFilter(name='CLOCK SPEED', type='multiselect', selection=['Below 1.5 GHz', 'Less than 900 MHz'], range=None)]) 

                    Input Query: {res} 
                    """,
                    usage = context.usage,
                    usage_limits = self.usage_limits,
                    output_type=List[UserFilter]
                )
                # logger.info(f'Gen User filters: {user_filters}')
                context.deps.search_specs.user_filters = user_filters.output
                step = f'Step {context.deps.steps}: prompt_user1 -> {len(user_filters.output) if user_filters.output else 0}'
                context.deps.flow.append(step)
                logger.info(step + f'\nUser filters: \n{user_filters.output}')
                # return user_filters.output

        @self.shop_agent.tool
        async def get_candidates(context: RunContext[ShopDeps]) -> List[Product] | None:
            """Get a list of filtered candidate products matching the user's query
            - Final Output 
            - use search query enriched with user details & rephrase_query along with user provided filters to get the final eligible candidates
            - End the user request & return them the relevant desired products
              """
            # logger.info(f'node get_candidates , deps: {context.deps}')
            context.deps.steps += 1
            best_site, search_query, user_filters = context.deps.search_specs.site, context.deps.query, context.deps.search_specs.user_filters
            # if user_filters:
            products = await get_filtered_products(context.deps.page, best_site, search_query, user_filters, top_k=top_k)
            if products and len(products) > 0:
                context.deps.candidates = products
            else:
                logger.info('Running fallback get_products')
                products = await get_filtered_products(context.deps.page, best_site, search_query, None, top_k=top_k)                
            step = f'Step {context.deps.steps}: get_candidates -> {len(products) if products else 0}'
            # logger.info(f'Products: {products}')
            await playwright_exit(context.deps.context_man)
            context.deps.context_man, context.deps.playwright, context.deps.browser, context.deps.context, context.deps.page = None, None, None, None, None
            context.deps.flow.append(step)
            logger.info(step + f'\nProduct:\n{products}')
            return products

        @self.shop_agent.output_validator
        def val_op(context:RunContext[ShopDeps], op: ShopResult) -> ShopResult:
            logger.info(f'pre op: {op}')
            op.flow = context.deps.flow
            op.steps = context.deps.steps
            op.products = context.deps.candidates if context.deps.candidates else []
            return op

        logger.info('Chatbot initialised !')

    async def chat(self, user_query: str, searchspecs: SearchSpecs = SearchSpecs()) -> Any:
        shop_deps = ShopDeps(query=user_query, llm=None , model_id=MODEL_ID, search_specs=searchspecs, candidates=[]) 
        res = await self.shop_agent.run(user_query, deps=shop_deps)
        logger.info(f'Final Answer: \n\n{res}')
        # for i, product in enumerate(res.output.products):
        #     logger.info(f'Product {i}: \n - Name: {product.name} \n - Price: {product.price} \n - Review: {product.review} \n - Link: {product.url}')
        logger.info(f'Recommended product: {res.output.recommended} \n{res.output.message} \nAgent Workflow: {res.output.flow}')
        logger.info(f'Usage: {res.usage()}')
        return res

async def main():
    while True:
        user_query = input('What do you want to SHOP today !!!\n')
        searchspecs = SearchSpecs()
        chatbot = Chatbot()
        await chatbot.chat(user_query, searchspecs)

if __name__ == "__main__":
   asyncio.run(main())
