import { evaluate } from '../connection.js';

const CHART_API = 'window.TradingViewApi._activeChartWidgetWV.value()';

export function registerIndicatorTools(server) {

  // ── 1. indicator_set_inputs — Change indicator settings ──

  server.tool('indicator_set_inputs', 'Change indicator/study input values (e.g., length, source, period)', {
    entity_id: { type: 'string', description: 'Entity ID of the study (from chart_get_state)' },
    inputs: { type: 'object', description: 'Object of input overrides, e.g. { length: 50, source: "close" }. Keys are input IDs, values are the new values.' },
  }, async ({ entity_id, inputs }) => {
    try {
      if (!entity_id) {
        return {
          content: [{ type: 'text', text: JSON.stringify({
            success: false,
            error: 'entity_id is required. Use chart_get_state to find study IDs.',
          }, null, 2) }],
          isError: true,
        };
      }

      if (!inputs || typeof inputs !== 'object' || Object.keys(inputs).length === 0) {
        return {
          content: [{ type: 'text', text: JSON.stringify({
            success: false,
            error: 'inputs must be a non-empty object, e.g. { length: 50 }',
          }, null, 2) }],
          isError: true,
        };
      }

      const escapedId = entity_id.replace(/'/g, "\\'");
      const inputsJson = JSON.stringify(inputs);

      const result = await evaluate(`
        (function() {
          var chart = ${CHART_API};
          var study = chart.getStudyById('${escapedId}');
          if (!study) return { error: 'Study not found: ${escapedId}' };

          var currentInputs = study.getInputValues();
          var overrides = ${inputsJson};
          var updatedKeys = {};

          for (var i = 0; i < currentInputs.length; i++) {
            if (overrides.hasOwnProperty(currentInputs[i].id)) {
              currentInputs[i].value = overrides[currentInputs[i].id];
              updatedKeys[currentInputs[i].id] = overrides[currentInputs[i].id];
            }
          }

          study.setInputValues(currentInputs);

          // Some complex studies recompile after setInputValues, making getInputValues()
          // temporarily return []. Return the values we set instead.
          var allInputs = study.getInputValues();
          return {
            updated_inputs: updatedKeys,
            all_inputs: allInputs.length > 0 ? allInputs : currentInputs,
            note: allInputs.length === 0 ? 'Study is recompiling — inputs shown are the values set' : undefined,
          };
        })()
      `);

      if (result && result.error) {
        return {
          content: [{ type: 'text', text: JSON.stringify({ success: false, error: result.error }, null, 2) }],
          isError: true,
        };
      }

      return {
        content: [{ type: 'text', text: JSON.stringify({
          success: true,
          entity_id,
          updated_inputs: result.updated_inputs,
          all_inputs: result.all_inputs,
        }, null, 2) }],
      };
    } catch (err) {
      return {
        content: [{ type: 'text', text: JSON.stringify({ success: false, error: err.message }, null, 2) }],
        isError: true,
      };
    }
  });

  // ── 2. indicator_toggle_visibility — Show/hide a study ──

  server.tool('indicator_toggle_visibility', 'Show or hide an indicator/study on the chart', {
    entity_id: { type: 'string', description: 'Entity ID of the study (from chart_get_state)' },
    visible: { type: 'boolean', description: 'true to show, false to hide' },
  }, async ({ entity_id, visible }) => {
    try {
      if (!entity_id) {
        return {
          content: [{ type: 'text', text: JSON.stringify({
            success: false,
            error: 'entity_id is required. Use chart_get_state to find study IDs.',
          }, null, 2) }],
          isError: true,
        };
      }

      if (typeof visible !== 'boolean') {
        return {
          content: [{ type: 'text', text: JSON.stringify({
            success: false,
            error: 'visible must be a boolean (true or false)',
          }, null, 2) }],
          isError: true,
        };
      }

      const escapedId = entity_id.replace(/'/g, "\\'");

      const result = await evaluate(`
        (function() {
          var chart = ${CHART_API};
          var study = chart.getStudyById('${escapedId}');
          if (!study) return { error: 'Study not found: ${escapedId}' };

          study.setVisible(${visible});
          var actualVisible = study.isVisible();

          return { visible: actualVisible };
        })()
      `);

      if (result && result.error) {
        return {
          content: [{ type: 'text', text: JSON.stringify({ success: false, error: result.error }, null, 2) }],
          isError: true,
        };
      }

      return {
        content: [{ type: 'text', text: JSON.stringify({
          success: true,
          entity_id,
          visible: result.visible,
        }, null, 2) }],
      };
    } catch (err) {
      return {
        content: [{ type: 'text', text: JSON.stringify({ success: false, error: err.message }, null, 2) }],
        isError: true,
      };
    }
  });
}
