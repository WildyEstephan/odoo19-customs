/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";

// Bank Cheque Management JavaScript
document.addEventListener("DOMContentLoaded", function() {
    console.log("Bank Cheque module loaded");
    
    // Solo ejecutar si estamos en la página de gestión de cheques
    if (!document.querySelector('#target')) {
        return;
    }
    
    const cheque_measure_unit = document.querySelector('#cheque_measure_unit')?.textContent || '';
    const cheque_height = document.querySelector('#cheque_height')?.textContent || '';
    const cheque_width = document.querySelector('#cheque_width')?.textContent || '';

    // Verificar si jQuery y Jcrop están disponibles
    if (typeof jQuery !== 'undefined' && jQuery.fn.Jcrop) {
        jQuery(function ($) {
            let jcrop_api;
            $('#target').Jcrop({
                onChange: showCoords,
                onSelect: showCoords,
                onRelease: clearCoords
            }, function () {
                jcrop_api = this;
            });

            $('#coords').on('change', 'input', function (e) {
                const x1 = $('#x1').val(),
                    x2 = $('#x2').val(),
                    y1 = $('#y1').val(),
                    y2 = $('#y2').val();
                if (jcrop_api) {
                    jcrop_api.setSelect([x1, y1, x2, y2]);
                }
            });

            // Event handlers
            function showCoords(c) {
                $('#x1').val(c.x);
                $('#y1').val(c.y);
                $('#x2').val(c.x2);
                $('#y2').val(c.y2);
                $('#w').val(c.w);
                $('#h').val(c.h);
            }
            
            function clearCoords() {
                $('#coords input').not("input[type='hidden']").val('');
            }
        });
    }
});
