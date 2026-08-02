from typing import Any, Iterable

from discord import app_commands

from ballsdex.core.utils.transformers import TTLModelTransformer

from ..models import GlobalShop, global_shops


class GlobalShopTransformer(TTLModelTransformer):
    name = "shop"
    model = GlobalShop

    async def load_items(self) -> Iterable[GlobalShop]:
        return global_shops.values()

    async def get_from_pk(self, value: int) -> Any:
        return await self.get_queryset().prefetch_related("items").aget(pk=value)


GlobalShopTransform = app_commands.Transform[GlobalShop, GlobalShopTransformer]
