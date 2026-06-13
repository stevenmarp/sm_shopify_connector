# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    shopify_instance_id = fields.Many2one('shopify.instance', string='Shopify Store', index=True)
    shopify_customer_gid = fields.Char(string='Shopify Customer GID', copy=False, index=True)
    shopify_last_imported = fields.Datetime(string='Shopify Last Imported', copy=False)
