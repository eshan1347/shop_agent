import json
from os import name, wait
from warnings import filters 
import playwright
import asyncio 
import time 
import re
import random
from typing import List, Optional, Dict, Any, Tuple
from playwright.async_api import async_playwright 
from pydantic_models import ProductReview, UserFilter, Product, ProductClass
import logging
import sys

logging.basicConfig(stream=sys.stderr, level=logging.INFO)
logger = logging.getLogger(__name__)

async def get_product_page(pro_url:str, page: Any) -> Product | None:
    try:
        await page.goto(pro_url)
        # await page.wait_for_selector('div._39kFie.N3De93.JxFEK3._48O0EI')
        pro_visuals = page.locator('div.DOjaWF.gdgoEp.col-5-12.MfqIAz')
        # await pro_visuals.first.wait_for(state='attached', timeout=1000)
        # img_ele = pro_visuals.locator('img.DByuf4.IZexXJ.jLEJ7H')
        img_ele = pro_visuals.locator('img').first
        img = await img_ele.get_attribute('src') if await img_ele.count() else None
        pro_desc = page.locator('div.DOjaWF.gdgoEp.col-8-12')
        pro_intro = page.locator('div.C7fEHH')
        name_ele = pro_intro.locator('h1._6EBuvT')
        name = await name_ele.inner_text()
        price_ele = pro_intro.locator('div.Nx9bqj.CxhGGd')
        price = await price_ele.inner_text() if price_ele else None
        rat_ele = pro_intro.locator('div.XQDdHH') # span.Y1HWO0 
        if await rat_ele.count():
            rat = await rat_ele.inner_text() 
            num_ele = pro_intro.locator('span.Wphh3N')
            if await num_ele.count():
                num_rat, num_rev = re.findall(r'[\d,]+', await num_ele.inner_text()) 
            else:
                num_rat, num_rev = '-1', '-1'
        else:
            rat = '0.0'
            num_rat, num_rev = '-1', '-1'
        prod_rev = ProductReview.model_validate({'ratings':rat , 'num_ratings': num_rat, 'num_reviews': num_rev})
        high = []
        product = Product.model_validate({'name': name, 'price': price, 'url': pro_url, 'image': img, 'review': prod_rev, 'details': high})
        return product
    except Exception as e:
        logger.error(f"Error while fetching {pro_url} deets: {e}")

async def get_products(base_url: str , page: Any) -> List[Product] | None:
    try:
        tiles = await page.query_selector_all("div.cPHDOP")
        logger.info(f'Tiles: {len(tiles)} | {tiles}')
        products = []
        for idx,tile in enumerate(tiles):
            try:
                link_ele = await tile.query_selector("a.CGtC98")
                link = await link_ele.get_attribute("href") if link_ele else None
                if link:
                    link = base_url + link
                logger.info('link:', link)
                # Product name
                name_ele = await tile.query_selector("div.KzDlHZ")
                name = await name_ele.inner_text() if name_ele else None
                logger.info('name:', name)
                # Price
                price_ele = await tile.query_selector("div.Nx9bqj._4b5DiR")
                price = await price_ele.inner_text() if price_ele else None
                logger.info('price:', price)
                # Image
                img_ele = await tile.query_selector("img.DByuf4")
                image = await img_ele.get_attribute("src") if img_ele else None
                logger.info('image:', image)
                #Ratings
                rat_ele = await tile.query_selector('div.XQDdHH')
                rat = await rat_ele.inner_text() if rat_ele else 0.0
                num_ele = await tile.query_selector('span.Wphh3N')
                num_rat, num_rev = re.findall(r'[\d,]+', await num_ele.inner_text()) if num_ele else ('-1', '-1')
                logger.info('ratings:', rat, num_rat, num_rev)
                #Highlights
                # ul_ele = await tile.query_selector('ul.G4BRas')
                # if ul_ele:
                li_ele = await tile.query_selector_all('li.J\\+igdf')
                high = []
                for li in li_ele:
                    if li:
                        high.append(await li.inner_text())
                logger.info('high:', high)
                # logger.info(f"{idx}. {name} | {price} | {link} | {image} | {rat} | {num_rat} | {num_rev} | {high}")
                if name and price and link and image:
                    # logger.info({'name': name, 'price': price, 'link': link, 'image': image, 'ratings': rat, 'num_ratings': num_rat, 'num_reviews': num_rev, 'mini_deets': high})
                    prod_rev = ProductReview.model_validate(
                        {'ratings':rat , 'num_ratings': num_rat, 'num_reviews': num_rev}
                    )
                    product = Product.model_validate(
                        {'name': name, 'price': price, 'url': link, 'image': image, 'review': prod_rev, 'details': high}
                    )
                    products.append(product)
            except Exception as e: 
                logger.error(f'Error processing tile {idx}: {e}')
        return products

    except Exception as e:
        logger.error(f"Error during browser setup or navigation: {e}")
        await page.screenshot(path="error_screenshot.png")
        await page.pause()

async def get_filters(page: Any, base_url: str, search_query:str) -> List[UserFilter] | None:
    # async with async_playwright() as p:
        try:
            # browser = await p.chromium.launch(headless=False)
            # context = await browser.new_context()
            # page = await context.new_page()

            await page.goto(base_url)
            await page.fill("input[name='q']", search_query)
            await page.press("input[name='q']", "Enter")
            await page.wait_for_selector('section._2OLUF3')

            # filters = await page.query_selector_all('section._2OLUF3')
            filters = page.locator('section._2OLUF3')
            fcount = await filters.count()
            logger.info(f'Filters: {fcount}')
            toggles = page.locator("svg.ukzDZP")
            site_filters = []

            for i in range(2, fcount):
                try:
                    filter = filters.nth(i)
                    fname = filter.locator('div.fxf7w6.rgHxCQ')
                    fname_count = await fname.count() 
                    if not fname or fname_count < 1:
                        continue
                    fname = (await fname.inner_text()).strip()
                    logger.info(f'Processing filter {fname} ...')
                    is_exp = filter.locator('div.SDsN9S')
                    if await is_exp.count() < 1:
                        logger.info(f'click click click ...')
                        header_toggle = filter.locator('svg.ukzDZP')
                        await header_toggle.click()
                        # await toggles.nth(i).click()
                        await page.wait_for_timeout(500)
                    sel = filter.locator('div.ewzVkT._3DvUAf')
                    rang = filter.locator('div._0vP2OD')
                    if sel:
                        opt = [(await sel.nth(e).inner_text()).strip() for e in range(await sel.count())]
                        # filterval = {
                        #     'type': 'multiselect',
                        #     'selection': opt,
                        #     'range': None
                        # }
                        site_filter = UserFilter.model_validate({'name': fname, 'type': 'multiselect' , 'selection': opt})
                    # elif rang:
                    #     opt = [(await rang.nth(e).inner_text()).strip() for e in range(await rang.count())]
                        # filterval = {
                        #     'type': 'range',
                        #     'selection': None,
                        #     'range': opt
                        # }
                        # site_filter = UserFilter.model_validate({'name': fname, 'type': 'range' , 'range': opt})
                    # logger.info(f'Pre Model: name: {fname}, value: {filterval}')
                    # site_filter = UserFilter.model_validate({'name': fname, 'value': filterval})
                    logger.info(f'Processed ! \n{site_filter}')
                    site_filters.append(site_filter)
                except Exception as e:
                    logger.error(f'Oops !!: {e}')
            return site_filters
                # all_texts = await filter.evaluate("""
                #     (element) => {
                #         const texts = [];
                #         // Iterate over all child nodes of the element
                #         element.childNodes.forEach(node => {
                #             // Get the text content and remove leading/trailing whitespace
                #             const text = node.textContent.trim();
                #             // Add it to our list only if it's not an empty string
                #             if (text) {
                #                 texts.push(text);
                #             }
                #         });
                #         return texts;
                #     }
                # """)
                # sel = re.split(r'(?=[A-Z0-9])', all_texts[-1])
                # sel = [s.strip() for s in sel if s]
                # sel = all_texts[-1]
                # print(f'{idx}. Filter: {all_texts[0]} | txt: {sel}')
                # For Range : _0vP2OD , Selection : ewzVkT _3DvUAf  
        except Exception as e:
            logger.error(f"Error during browser setup or navigation: {e}")
            await page.screenshot(path="error_screenshot.png")
            await page.pause()
            return []

async def get_filtered_products(page: Any, base_url: str, search_query: str, user_filters: List[UserFilter] | None, top_k:int = 10) -> List[Product] | None:
    # async with async_playwright() as p:
        try:
            await page.goto(base_url)
            # search_url = base_url + f'search?q={search_query.replace(" ", "+")}'
            # await page.goto(search_url)
            await page.fill("input[name='q']", search_query)
            await page.press("input[name='q']", "Enter")
            await page.wait_for_selector("div.DOjaWF.gdgoEp")

            if user_filters:
                filters = page.locator('section._2OLUF3')
                fcount = await filters.count()
                user_fnames = [ f.name for f in user_filters]
                user_fn2vals = {f.name: f.selection for f in user_filters}
                for i in range(2, fcount):
                    try:
                        filter = filters.nth(i)
                        fname = filter.locator('div.fxf7w6.rgHxCQ')
                        fname_count = await fname.count() 
                        if not fname or fname_count < 1:
                            continue
                        fname = (await fname.inner_text()).strip()
                        logger.info(f'Applying {fname} filter')
                        if fname not in user_fnames:
                            continue
                        logger.info(f'Applying filter {fname} ...')
                        is_exp = filter.locator('div.SDsN9S')
                        if await is_exp.count() < 1:
                            logger.info(f'click click click ...')
                            header_toggle = filter.locator('svg.ukzDZP')
                            await header_toggle.click()
                            # await toggles.nth(i).click()
                            # await page.wait_for_timeout(500)
                        # when you know desired values:
                        vals = user_fn2vals.get(fname, None)
                        if vals:
                            for wanted in vals:
                                try:
                                    # restrict the search to this filter's option elements
                                    locator = filter.locator('div.ewzVkT._3DvUAf', has_text=wanted)
                                    # small wait — the locator will throw quickly if not found
                                    await locator.first.wait_for(state='attached', timeout=1000)
                                    await locator.first.scroll_into_view_if_needed()
                                    await locator.first.click(timeout=1000)
                                    logger.info(f"Selected {wanted} in {fname}")
                                except Exception as e:
                                    logger.error(f"couldn't select {wanted} in {fname}: {e}")

                        # sel = filter.locator('div.ewzVkT._3DvUAf')
                        # rang = filter.locator('div._0vP2OD')
                        # if sel:
                        #     ocount = await sel.count()
                        #     for e in range(ocount):
                        #         try: 
                        #             # filtername = (await sel.nth(e).inner_text()).strip() 
                        #             filtername = await sel.nth(e).text_content(timeout=1000)
                        #             filtername = filtername.strip() if filtername else ''
                        #             logger.info(f'Trying {filtername} uwu')
                        #         except Exception as e:
                        #             logger.info(f'f: {e}')
                        #             continue
                        #         # locator = filter.locator('div.ewzVkT._3DvUAf', has_text=filtername)
                        #         # await locator.wait_for(timeout=5000)
                        #         # await locator.click()
                        #         # logger.info(f"Selected {filtername} in {fname} ...")
                        #         if user_fn2vals[fname] and filtername in user_fn2vals[fname]:
                        #             await sel.nth(e).scroll_into_view_if_needed()
                        #             await sel.nth(e).click()
                        #             # await page.wait_for_timeout(500)
                        #             logger.info(f'Selected {filtername} in {fname} ...')
                        # elif rang:
                        #     opt = [(await rang.nth(e).inner_text()).strip() for e in range(await rang.count())]
                        #     filterval = {
                        #         'type': 'range',
                        #         'range': opt
                        #     }
                        # await page.wait_for_timeout(1000)
                    except Exception as e:
                        logger.error(f'Oops !!: {e}')
            pro_links = await get_pro_links(base_url, page)
            products = []
            for pro_link in pro_links[:top_k]:
                products.append( await get_product_page(pro_link, page))
            return products
            # return await get_products(base_url, page) 
        except Exception as e:
            logger.error(f'Oopsie ! {e}')

async def get_pro_links(base_url: str, page:Any) -> List[str]:
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    link_eles = await page.locator("div.DOjaWF.gdgoEp div.cPHDOP a").all()
    # link_eles = await page.locator("a.CGtC98").all()
    # link_count = await link_eles.count()
    # if link_count < 1:
    #     link_eles = page.locator("a.CGtC98")
    #     link_count = await link_eles.count()
    logger.info(f'{len(link_eles)} product links fetched !')
    links = []
    for i,link_ele in enumerate(link_eles):
        try:
            # link = await link_eles.nth(e).get_attribute("href")
            link = await link_ele.get_attribute("href")
            if link and 'page=' not in link and 'search?' not in link and len(link) > 150:
                link = base_url + link
                # logger.info(f'{e}. {link}')
                if link not in links:
                    links.append(link)
        except Exception as e:
            logger.error(f'Oopsie in get_pro_links: {e}')
    logger.info(f'links: {len(links)}')
    return links[1:]

async def playwright_enter() -> Tuple:
    context_man = async_playwright()
    playwright = await context_man.__aenter__()
    browser = await playwright.chromium.launch(headless=True) #False for browser
    context = await browser.new_context()
    page = await context.new_page()
    page.set_default_timeout(15000)          # 6 seconds for all waits
    page.set_default_navigation_timeout(15000)  
    return context_man, playwright, browser, context, page

async def playwright_exit(context_man) -> None:
    await context_man.__aexit__(None, None, None)

async def main():
    base_url = 'https://www.flipkart.com'
    search_query = 'Real Madrid 16/17 blue jersey'
    pro_url = 'https://www.flipkart.com/apple-iphone-16-black-256-gb/p/itm86da1977dcdf1?pid=MOBH4DQFZCJJXUFG&lid=LSTMOBH4DQFZCJJXUFGO5DY3W&marketplace=FLIPKART&q=iphones&store=tyy%2F4io&spotlightTagId=default_BestsellerId_tyy%2F4io&srno=s_1_1&otracker=search&otracker1=search&fm=Search&iid=ebc6ba69-a89c-454d-89fc-28840c990f28.MOBH4DQFZCJJXUFG.SEARCH&ppt=sp&ppn=sp&ssid=kbfoyqc2aiya8utc1758898276696&qH=3e7fa8c51e2e4986'
    pro_url = """https://www.flipkart.com/yellowvibes-printed-typography-men-polo-neck-white-t-shirt/p/itm1a98ebe03b5ec?pid=TSHGWEPXUAPRMKYR&lid=LSTTSHGWEPXUAPRMKYRQIO4IO&marketplace=FLIPKART&q=Real+Madrid+16%2F17+blue+jersey
&store=clo%2Fash%2Fank&srno=s_1_1&otracker=search&otracker1=search&fm=organic&iid=en_oFB3vt2XCktASEkPfAibC4Z1DeYhIw7ZGQqZLNQPWOWPAg129Gg2Hhmsqf-_kVmqB9SCXfJYY1jeUE-T3l3eNg%3D%3D&ppt=None&ppn=None&ssid=z37yvkk2tc0
000001758907408893&qH=b0f06ba87382280b
"""
# yellowvibes
    # await get_filters(base_url, 'iphones !latest one black with 512 gb into latest iPhone, black, 512GB')
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
    #
    #     await page.goto(base_url)
    #     # search_url = base_url + f'search?q={search_query.replace(" ", "+")}'
    #     # await page.goto(search_url)
    #     await page.fill("input[name='q']", search_query)
    #     await page.press("input[name='q']", "Enter")
    #     await page.wait_for_selector("div.DOjaWF.gdgoEp")

        # res = await get_products(base_url, page)
        # res = await get_product_page(pro_url, page)
        # res = await get_pro_links(base_url, page)
        # logger.info(len(res))
        # user_filters = [{'name': 'RAM', 'value': {'type': 'multiselect', 'selection': ['4 GB'] }}] 
        # user_filters = [UserFilter(name='RAM', type='multiselect', selection=['4 GB'])]
        user_filters = [UserFilter(name='INTERNAL STORAGE', type='multiselect', selection=['256 GB & Above', '128 - 255.9 GB', '64 - 127.9 GB', '32 - 63.9 GB', '16 - 31.9 GB', '8 - 15.9 GB', '4 - 7.9 GB', 'Less than 1 GB', '256 GB Above'], range=None), UserFilter(name='SIM TYPE', type='multiselect', selection=['Dual Sim', 'Dual Sim(Nano + eSIM)', 'Single Sim'], range=None)]
        res = await get_filtered_products(page, base_url, search_query, user_filters, top_k=5)
        logger.info(res)

# TSHH6F3Y3XZ7WBN3 | _1sdMkc LFEi7Z

if __name__ == "__main__":
    asyncio.run(main())
