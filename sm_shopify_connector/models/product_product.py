# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    shopify_instance_id = fields.Many2one('shopify.instance', string='Shopify Store', index=True)
    shopify_product_gid = fields.Char(string='Shopify Product GID', copy=False, index=True)
    shopify_variant_gid = fields.Char(string='Shopify Variant GID', copy=False, index=True)
    shopify_inventory_item_gid = fields.Char(string='Shopify Inventory Item GID', copy=False, index=True)
    shopify_last_imported = fields.Datetime(string='Shopify Last Imported', copy=False)
