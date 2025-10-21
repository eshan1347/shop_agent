from typing import List
import html
import streamlit as st
import asyncio
from pydantic_models import Product
from pydantic_ai_agents import Chatbot

CARD_CSS = """
<style>
.card {
  border: 1px solid #e6e6e6;
  border-radius: 12px;
  padding: 10px;
  margin: 6px 0;
  box-shadow: 0 2px 6px rgba(0,0,0,0.03);
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}
.card-img {
  width: 100%;
  height: 180px;
  object-fit: contain;
  background: #fff;
  border-radius: 8px;
}
.card-body { padding-top: 8px; }
.card-title {
  font-size: 14px;
  font-weight: 600;
  line-height: 1.2;
  margin-bottom: 6px;
}
.card-price { font-size: 15px; font-weight: 700; margin-bottom: 6px; color: #1b6bff; }
.card-rating { font-size: 13px; color: #666; margin-bottom: 6px; }
.card-actions { margin-top: 8px; }
a.card-link { text-decoration: none; color: inherit; }
</style>
"""

# class ProductReview(BaseModel):
#     ratings: Annotated[float, Field(le=5.0, ge=0.0)] = 0.0
#     num_ratings: int = -1
#     num_reviews : int = -1
#
# class Product(BaseModel): 
#     id: Optional[str] = None
#     pro_class : Annotated[Optional[ProductClass] ,Field(description="The category/type of the product")] = None
#     price: int 
#     name: str
#     url: str
#     image: Optional[str] 
#     review: Optional[ProductReview] 
#     details: List[str]
#     delivery_date: datetime.date | str | None = None

def render_products(products: List[Product], cols: int = 3):
    rows = [products[i : i + cols] for i in range(0, len(products), cols)]
    for row in rows:
        columns = st.columns(len(row), gap="large")
        for col, product in zip(columns, row):
            with col:
                # Card HTML
                name_escaped = html.escape(product.name)
                url = product.url
                image = product.image if product.image else None
                price = product.price 
                rating = product.review.ratings if product.review else None
                num_ratings = product.review.num_ratings if product.review else None

                # If price is numeric, format it with comma separators
                if isinstance(price, (int, float)):
                    price_str = "₹{:,.0f}".format(price)
                else:
                    price_str = str(price) if price else ""

                # Build HTML for the card (image + title link)
                if image:
                    card_html = f"""
                    <div class="card">
                    <div>
                        <a class="card-link" href="{html.escape(url)}" target="_blank">
                        <img class="card-img" src="{html.escape(image)}" alt="{name_escaped}" />
                        </a>
                        <div class="card-body">
                        <a class="card-link" href="{html.escape(url)}" target="_blank">
                            <div class="card-title">{name_escaped}</div>
                        </a>
                        <div class="card-price">{price_str}</div>
                        <div class="card-rating">{"⭐ " + str(rating) if rating else ""}{" (" + str(num_ratings) + ")" if num_ratings else ""}</div>
                        </div>
                    </div>
                    </div>
                    """
                else:
                    card_html = f"""
                    <div class="card">
                    <div>
                        <a class="card-link" href="{html.escape(url)}" target="_blank">
                        <img class="card-img" src="https://www.google.com/url?sa=i&url=https%3A%2F%2Fagrimart.in%2Findex.php%2Fhome%2Fvendor_profile%2Fget_slider%2F&psig=AOvVaw26r_Mo9n81yi0zt3Ujwbet&ust=1759059432925000&source=images&cd=vfe&opi=89978449&ved=0CBIQjRxqFwoTCOCwn5ft-I8DFQAAAAAdAAAAABAK" alt="default-image" />
                        </a>
                        <div class="card-body">
                        <a class="card-link" href="{html.escape(url)}" target="_blank">
                            <div class="card-title">{name_escaped}</div>
                        </a>
                        <div class="card-price">{price_str}</div>
                        <div class="card-rating">{"⭐ " + str(rating) if rating else ""}{" (" + str(num_ratings) + ")" if num_ratings else ""}</div>
                        </div>
                    </div>
                    </div>
                    """

                st.markdown(card_html, unsafe_allow_html=True)

async def st_main():
# Page config
    st.set_page_config(page_title="Shopping assistant", page_icon="💬")
    st.title("💬 Shopping Assistant")
    st.write("What would you like to buy today?")
    st.markdown(CARD_CSS, unsafe_allow_html=True)

    chatbot = Chatbot()

# Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []

# Display chat history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

# Chat input box
    if user_input := st.chat_input("Type your message..."):
        # Add user message to history
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        # Get bot response
        resp = await chatbot.chat(user_input)
        op = f"""
        Recommended product: \n{resp.output.recommended.model_dump_json()}
        \n{resp.output.message}\n Agent Flow : {resp.output.flow}
        """
        st.session_state.messages.append({"role": "assistant", "content": op})
        with st.chat_message("assistant"):
            st.markdown(op)
            render_products(resp.products)

if __name__ == "__main__":
    asyncio.run(main())
