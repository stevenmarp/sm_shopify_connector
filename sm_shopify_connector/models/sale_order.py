# -*- coding: utf-8 -*-
from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    shopify_instance_id = fields.Many2one('shopify.instance', string='Shopify Store', index=True)
    shopify_order_gid = fields.Char(string='Shopify Order GID', copy=False, index=True)
    shopify_order_name = fields.Char(string='Shopify Order Name', copy=False)
    shopify_financial_status = fields.Char(string='Shopify Financial Status', copy=False)
    shopify_fulfillment_status = fields.Char(string='Shopify Fulfillment Status', copy=False)
    shopify_last_imported = fields.Datetime(string='Shopify Last Imported', copy=False)
