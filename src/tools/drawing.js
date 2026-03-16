import { evaluate, getChartApi } from '../connection.js';

export function registerDrawingTools(server) {

  server.tool('draw_shape', 'Draw a shape/line on the chart', {
    shape: { type: 'string', description: 'Shape type: horizontal_line, vertical_line, trend_line, rectangle, text' },
    point: { type: 'object', description: '{ time: unix_timestamp, price: number }' },
    point2: { type: 'object', description: 'Second point for two-point shapes (trend_line, rectangle)', default: null },
    overrides: { type: 'object', description: 'Style overrides (e.g., { linecolor: "#ff0000", linewidth: 2 })', default: {} },
    text: { type: 'string', description: 'Text content for text shapes', default: '' },
  }, async ({ shape, point, point2, overrides, text }) => {
    try {
      const apiPath = await getChartApi();
      const overridesStr = JSON.stringify(overrides || {});
      const textStr = text ? JSON.stringify(text) : '""';

      let result;
      if (point2) {
        result = await evaluate(`
          (function() {
            var api = ${apiPath};
            var points = [
              { time: ${point.time}, price: ${point.price} },
              { time: ${point2.time}, price: ${point2.price} }
            ];
            var id = api.createMultipointShape(points, {
              shape: '${shape}',
              overrides: ${overridesStr},
              text: ${textStr},
            });
            return { entity_id: id };
          })()
        `);
      } else {
        result = await evaluate(`
          (function() {
            var api = ${apiPath};
            var id = api.createShape(
              { time: ${point.time}, price: ${point.price} },
              { shape: '${shape}', overrides: ${overridesStr}, text: ${textStr} }
            );
            return { entity_id: id };
          })()
        `);
      }

      return {
        content: [{ type: 'text', text: JSON.stringify({
          success: true,
          shape,
          entity_id: result?.entity_id,
        }, null, 2) }],
      };
    } catch (err) {
      return {
        content: [{ type: 'text', text: JSON.stringify({ success: false, error: err.message }, null, 2) }],
        isError: true,
      };
    }
  });

  server.tool('draw_list', 'List all shapes/drawings on the chart', {}, async () => {
    try {
      const apiPath = await getChartApi();
      const shapes = await evaluate(`
        (function() {
          var api = ${apiPath};
          var all = api.getAllShapes();
          return all.map(function(s) { return { id: s.id, name: s.name }; });
        })()
      `);

      return {
        content: [{ type: 'text', text: JSON.stringify({
          success: true,
          count: shapes?.length || 0,
          shapes: shapes || [],
        }, null, 2) }],
      };
    } catch (err) {
      return {
        content: [{ type: 'text', text: JSON.stringify({ success: false, error: err.message }, null, 2) }],
        isError: true,
      };
    }
  });

  server.tool('draw_clear', 'Remove all drawings from the chart', {}, async () => {
    try {
      const apiPath = await getChartApi();
      await evaluate(`${apiPath}.removeAllShapes()`);

      return {
        content: [{ type: 'text', text: JSON.stringify({ success: true, action: 'all_shapes_removed' }, null, 2) }],
      };
    } catch (err) {
      return {
        content: [{ type: 'text', text: JSON.stringify({ success: false, error: err.message }, null, 2) }],
        isError: true,
      };
    }
  });

  // ── Remove Single Drawing ───────────────────────────────────────────
  server.tool('draw_remove_one', 'Remove a specific drawing by entity ID', {
    entity_id: { type: 'string', description: 'Entity ID of the drawing to remove (from draw_list)' },
  }, async ({ entity_id }) => {
    try {
      const apiPath = await getChartApi();
      const result = await evaluate(`
        (function() {
          var api = ${apiPath};
          var eid = '${entity_id}';

          // Verify the shape exists before removal
          var before = api.getAllShapes();
          var found = false;
          for (var i = 0; i < before.length; i++) {
            if (before[i].id === eid) { found = true; break; }
          }
          if (!found) {
            return { removed: false, error: 'Shape not found: ' + eid, available: before.map(function(s) { return s.id; }) };
          }

          // Remove it
          api.removeEntity(eid);

          // Verify removal
          var after = api.getAllShapes();
          var stillExists = false;
          for (var j = 0; j < after.length; j++) {
            if (after[j].id === eid) { stillExists = true; break; }
          }

          return { removed: !stillExists, entity_id: eid, remaining_shapes: after.length };
        })()
      `);

      if (result?.error) {
        return {
          content: [{ type: 'text', text: JSON.stringify({ success: false, ...result }, null, 2) }],
          isError: true,
        };
      }

      return {
        content: [{ type: 'text', text: JSON.stringify({
          success: true,
          entity_id: result?.entity_id,
          removed: result?.removed,
          remaining_shapes: result?.remaining_shapes,
        }, null, 2) }],
      };
    } catch (err) {
      return {
        content: [{ type: 'text', text: JSON.stringify({ success: false, error: err.message }, null, 2) }],
        isError: true,
      };
    }
  });

  // ── Get Drawing Properties ──────────────────────────────────────────
  server.tool('draw_get_properties', 'Get properties and points of a specific drawing', {
    entity_id: { type: 'string', description: 'Entity ID of the drawing (from draw_list)' },
  }, async ({ entity_id }) => {
    try {
      const apiPath = await getChartApi();
      const result = await evaluate(`
        (function() {
          var api = ${apiPath};
          var eid = '${entity_id}';
          var props = { entity_id: eid };

          // Get the shape object
          var shape = api.getShapeById(eid);
          if (!shape) {
            return { error: 'Shape not found: ' + eid };
          }

          // Discover available methods
          var methods = [];
          try {
            for (var key in shape) {
              if (typeof shape[key] === 'function') methods.push(key);
            }
            props.available_methods = methods;
          } catch(e) {}

          // Try to read points
          try {
            var pts = shape.getPoints();
            if (pts) props.points = pts;
          } catch(e) { props.points_error = e.message; }

          // Try to read properties/overrides
          try {
            var ovr = shape.getProperties();
            if (ovr) props.properties = ovr;
          } catch(e) {
            try {
              var ovr2 = shape.properties();
              if (ovr2) props.properties = ovr2;
            } catch(e2) { props.properties_error = e2.message; }
          }

          // Try isVisible
          try { props.visible = shape.isVisible(); } catch(e) {}

          // Try isLocked
          try { props.locked = shape.isLocked(); } catch(e) {}

          // Try isSelectionEnabled
          try { props.selectable = shape.isSelectionEnabled(); } catch(e) {}

          // Try to get name/type info from the shape list
          try {
            var all = api.getAllShapes();
            for (var i = 0; i < all.length; i++) {
              if (all[i].id === eid) {
                props.name = all[i].name;
                break;
              }
            }
          } catch(e) {}

          return props;
        })()
      `);

      if (result?.error) {
        return {
          content: [{ type: 'text', text: JSON.stringify({ success: false, ...result }, null, 2) }],
          isError: true,
        };
      }

      return {
        content: [{ type: 'text', text: JSON.stringify({ success: true, ...result }, null, 2) }],
      };
    } catch (err) {
      return {
        content: [{ type: 'text', text: JSON.stringify({ success: false, error: err.message }, null, 2) }],
        isError: true,
      };
    }
  });
}
