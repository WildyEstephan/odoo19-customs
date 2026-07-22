odoo.define('dgii_report.dgii_report_widget', function (require) {
    "use strict";

    var basicFields = require('web.basic_fields');
    var field_registry = require('web.field_registry');
   
    var UrlDgiiReportsWidget = basicFields.UrlWidget.extend({
        _renderReadonly: function () {
            this.$el.text(this.attrs.text || this.value)
                .addClass('o_form_uri o_text_overflow')
                .attr('target', '_blank')
                .attr('href', "dgii_reports/"+this.value);
        },
    });
    field_registry.add('dgii_reports_url', UrlDgiiReportsWidget);

    return {
        UrlDgiiReportsWidget: UrlDgiiReportsWidget,
    };

});