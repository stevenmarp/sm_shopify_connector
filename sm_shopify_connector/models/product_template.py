# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    shopify_instance_id = fields.Many2one('shopify.instance', string='Shopify Store', index=True)
    shopify_product_gid = fields.Char(string='Shopify Product GID', copy=False, index=True)
    shopify_handle = fields.Char(string='Shopify Handle', copy=False)
    shopify_status = fields.Char(string='Shopify Status', copy=False)
    shopify_vendor = fields.Char(string='Shopify Vendor', copy=False)
    shopify_product_type = fields.Char(string='Shopify Product Type', copy=False)
    shopify_tags = fields.Char(string='Shopify Tags', copy=False)
    shopify_last_imported = fields.Datetime(string='Shopify Last Imported', copy=False)
