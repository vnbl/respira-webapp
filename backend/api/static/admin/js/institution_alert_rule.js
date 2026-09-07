/**
 * Keeps the sensor select showing only the chosen institution's own sensor.
 *
 * The form already narrows the field server-side, so a wrong station cannot be
 * saved with or without this file. What this adds is seeing the narrowing while
 * filling the form instead of discovering it on submit: pick an institution and
 * its sensor appears, already selected, because there is only ever one.
 *
 * The institution field is an autocomplete, which the admin upgrades to Select2
 * — and Select2 replaces the element's own change events with jQuery ones. Two
 * consequences drive how this is written:
 *
 *   * The listener has to be bound through `django.jQuery`, since a native
 *     `addEventListener('change')` never fires once Select2 owns the field.
 *   * It has to be bound *after* the admin initialises the widget, which it
 *     does on its own DOMContentLoaded handler. Binding on plain
 *     DOMContentLoaded races that and usually loses, so this waits for the
 *     window `load` event instead, by which point every admin script has run.
 */
(function () {
  'use strict';

  var LOOKUP_URL = 'contracted-station/';

  function start() {
    var institutionField = document.getElementById('id_institution');
    var stationField = document.getElementById('id_station');
    if (!institutionField || !stationField) {
      return;
    }

    // Relative to the current admin page (…/add/ or …/<pk>/change/), which is
    // what keeps this working under a mounted admin prefix.
    var base = window.location.pathname.replace(/(add|\d+\/change)\/$/, '');

    function setOptions(station) {
      // Rebuilt rather than filtered: the previous institution's sensor must
      // not stay selectable, and an empty list is the honest state when the
      // institution has no contract.
      stationField.innerHTML = '';

      var option = document.createElement('option');
      if (!station) {
        option.value = '';
        option.textContent = '(no sensor under contract)';
      } else {
        option.value = station.id;
        option.textContent = station.name;
        option.selected = true;
      }
      stationField.appendChild(option);
    }

    function refresh() {
      var institutionId = institutionField.value;
      if (!institutionId) {
        setOptions(null);
        return;
      }

      fetch(base + LOOKUP_URL + '?institution=' + encodeURIComponent(institutionId), {
        credentials: 'same-origin',
      })
        .then(function (response) {
          return response.ok ? response.json() : { station: null };
        })
        .then(function (data) {
          setOptions(data.station);
        })
        .catch(function () {
          // Leaving the select as it stands is safer than emptying it: the
          // server still resolves a blank station from the contract, so a
          // failed lookup costs the preview and nothing else.
        });
    }

    var jq = window.django && window.django.jQuery;
    if (jq) {
      // `select2:select` covers picking from the dropdown; `change` covers the
      // clear button and any programmatic change.
      jq(institutionField).on('select2:select select2:clear change', refresh);
    } else {
      institutionField.addEventListener('change', refresh);
    }

    // An institution already chosen when the page opens — editing an existing
    // alert, or an add form redisplayed after a validation error — needs the
    // list populated without waiting for a change that may never come.
    if (institutionField.value) {
      refresh();
    }
  }

  // `load`, not `DOMContentLoaded`: the admin initialises Select2 on its own
  // DOMContentLoaded handler, and binding before that leaves the listener on an
  // element Select2 then stops emitting events for.
  if (document.readyState === 'complete') {
    start();
  } else {
    window.addEventListener('load', start);
  }
})();
