# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ShopifySyncLog(models.Model):
    _name = 'shopify.sync.log'
    _description = 'Shopify Sync Log'
    _order = 'create_date desc, id desc'

    name = fields.Char(required=True)
    instance_id = fields.Many2one('shopify.instance', required=True, ondelete='cascade')
    operation = fields.Selection([
        ('connection', 'Connection'),
        ('product', 'Product Import'),
        ('customer', 'Customer Import'),
        ('order', 'Order Import'),
        ('all', 'Full Sync'),
    ], required=True)
    state = fields.Selection([
        ('success', 'Success'),
        ('warning', 'Warning'),
        ('failed', 'Failed'),
    ], default='success', required=True)
    records_processed = fields.Integer(default=0)
    message = fields.Text()

    @api.model
    def sm_log(self, instance, operation, state='success', records_processed=0, message=False):
        return self.sudo().create({
            'name': dict(self._fields['operation'].selection).get(operation, operation),
            'instance_id': instance.id,
            'operation': operation,
            'state': state,
            'records_processed': records_processed,
            'message': message or '',
        })
