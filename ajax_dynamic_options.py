#!/usr/bin/env python
"""Custom script which adds next-gen sequencing defaults to a galaxy database.

This adds the basic parts we will be building off of to track and manage
sequencing results.

See tool-data/nglims.yaml for the configuration file to adjust the same request
information.

While testing, you can remove all of your current data with:

    DELETE FROM form_values;
    DELETE FROM sample_event;
    DELETE FROM sample_request_map;
    DELETE FROM sample;
    DELETE FROM request_event;
    DELETE FROM request

Then all of the definitions with:
    DELETE FROM sample_state;
    DELETE FROM request_type;
    update form_definition_current SET latest_form_id = NULL;
    DELETE FROM form_definition;
    DELETE FROM form_definition_current;

Usage:
    add_ng_defaults.py <ini file>
"""
import os
import sys
import time, ConfigParser
from optparse import OptionParser
import yaml

new_path = [ os.path.join( os.getcwd(), "lib" ) ]
new_path.extend( sys.path[1:] ) # remove scripts/ from the path
sys.path = new_path

from galaxy import eggs
import pkg_resources

import galaxy.model.mapping
from galaxy import model, config

import logging
LOG_FORMAT = '%(asctime)s|%(levelname)-8s|%(message)s'
LOG_DATEFMT = '%Y-%m-%d %H:%M:%S'
LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']

pkg_resources.require( "SQLAlchemy >= 0.4" )

def main(ini_file):
    global logger

    # Initializing logger
    logger = init_logger(logging)

    conf_parser = ConfigParser.ConfigParser({'here':os.getcwd()})
    logger.info('Reading galaxy.ini')
    conf_parser.read(ini_file)
    ini_config = dict()
    for key, value in conf_parser.items("app:main"):
        ini_config[key] = value
    ini_config = config.Configuration(**ini_config)
    logger.info('Reading ajax config file from galaxy.ini')
    #ajax_config_file = ini_config.get("ajax_dynamic_options_config_file", None)
    ajax_config_file = ini_config.get("ajax_dynamic_options_config_file", "/galaxy-central/scripts/tools/ajax_dynamic_options.conf.yaml")
    if not ajax_config_file:
        raise ValueError("Need to specify ajax configuration in universe_wsgi")
    in_handle = open(ajax_config_file)
    ajax_config = yaml.load(in_handle)
    in_handle.close()
    db_con = ini_config.database_connection
    if not db_con:
        #db_con = "sqlite:///%s?isolation_level=IMMEDIATE" % ini_config.database
        db_con = "postgresql://galaxy:galaxy@localhost:5432/galaxy"
    app = SimpleApp(db_con, ini_config.file_path)

    top_level_type = create_default_requests(app,ajax_config["user"])
    update_existing_user(app,ajax_config["user"],"User Registration Form")


def init_logger(logging):
    log_level = LOG_LEVELS[1]
    kwargs = {
        'format'  : LOG_FORMAT,
        'datefmt' : LOG_DATEFMT,
        'level'   : log_level}

    logging.basicConfig(**kwargs)

    logger = logging.getLogger('ajax_dynamic_options')
    return logger


class RequestDef:
    def __init__(self, name, form_type, fields, form_only = False):
        self.name = name
        self.form_type = form_type
        self.fields = fields
        self.form_only = form_only

    def add_form_definition(self, app, update_fields=False):
        form = app.sa_session.query(app.model.FormDefinition).filter_by(
            name=self.name).first()
        fields, tooltips = self._get_fields()
        if form is None:
            form = app.model.FormDefinition(self.name, "", fields,
                    form_type=self.form_type, layout=[])
            form_curr = app.model.FormDefinitionCurrent(form)
            form.form_definition_current = form_curr
            app.sa_session.add(form_curr)
            app.sa_session.add(form)
        # if we are consistent with our fields, add the new data
        elif len(fields) == len(form.fields):
            form.fields = fields
        else:
            self._update_values(form, fields, app)
            form.fields = fields
        app.sa_session.flush()
        # add or update tooltips for each of the fields
        tt_fields = []
        for i, field in enumerate(form.fields):
            if tooltips.get(i, ""):
                field['title'] = tooltips[i]
            tt_fields.append(field)
        form.fields = tt_fields
        app.sa_session.flush()
        return form

    def _update_values(self, form, new_fields, app):
        """Update values to match the new form fields.

        This requires that you don't change the labels of the old
        fields while trying to add new items. Do one at a time.
        """
        is_delete = len(new_fields) < form.fields
        new_labels = [f["label"] for f in new_fields]
        if not is_delete:
            for old_label in (f["label"] for f in form.fields):
                assert old_label in new_labels, "Form label changed: %s" % old_label
        label_to_name = dict()
        for f in form.fields:
            label_to_name[f["label"]] = f["name"]
        label_remap = dict()
        new_info = dict()
        for f in new_fields:
            if f["label"] in label_to_name:
                label_remap[label_to_name[f["label"]]] = f["name"]
            else:
                new_info[f["name"]] = ""

        for form_val in app.sa_session.query(app.model.FormValues
                ).filter_by(form_definition_id = form.id):
            new_content = dict()
            for key, val in form_val.content.items():
                try:
                    new_key = label_remap[key]
                except KeyError:
                    if is_delete:
                        new_key = "deleted_%s" % key
                    else:
                        raise
                new_content[new_key] = val
            new_content.update(new_info)
            form_val.content = new_content

    def _get_fields(self):
        final_fields = []
        tooltips = {}
        for i, field in enumerate(self.fields):
            ftype = "TextField"
            tooltip = ""
            required = True
            freetext = False
            selectf = None
            if isinstance(field, str):
                name = field
            elif len(field) == 2:
                name, tooltip = field
            elif len(field) == 3:
                name, tooltip, ftype = field
            elif len(field) == 5:
                name, tooltip, ftype, required, freetext = field
            else:
                print field
                raise NotImplementedError
            if isinstance(ftype, list):
                selectf = ftype
                ftype = "ComboboxField"
                if freetext:
                    ftype += "_freetext"
                required = False
            cur_field = self._get_field(name, required, ftype, i, selectf)
            final_fields.append(cur_field)
            tooltips[i] = tooltip
        return final_fields, tooltips

    def _get_field(self, name, required, ftype, pos, selectlist=None):
        if required:
            required = "required"
        else:
            required = "optional"
        base = dict(
                name = "field_%s" % pos,
                label = name,
                required = required,
                type = ftype,
                layout = "%s" % pos,
                helptext = "",
                visible = True)
        if selectlist is not None:
            base['selectlist'] = selectlist
        return base

def _get_form_items(form):
    """Retrieve the input form elements from a configuration.
    """
    final = []
    for item in form:
        label = item["label"]
        tooltip = item.get("tooltip", "")
        itype = item.get("type", "TextField")
        required = item.get("required", True)
        freetext = item.get("freetext", False)
        final.append((label, tooltip, itype, required, freetext))
    return final

def create_default_requests(app, user_conf):
    """Create a set of possible sequencing and preparation requests.
    """
    top_level_type = None
    requests = []
    # start with specific forms for users
    user_form = user_conf["form"]
    logger.info("User Registration Form")
    requests.append(RequestDef("User Registration Form",
        model.FormDefinition.types.get("USER_INFO"),
        _get_form_items(user_form), True))

    for i, request in enumerate(requests):
        logger.info("Adding/Updating Form Definition")
        form = request.add_form_definition(app, i == 0)
        app.sa_session.flush()

    return top_level_type


def _get_form_values(app, form, params):
    values = {}
    for field in form.fields:
        k = field["label"].replace(" ", "_").lower()
        values[field["name"]] = params.get(k, "")
    return app.model.FormValues(form, values)

def update_existing_user(app,user_conf,form_name):
    logger.info('Updating existing Form User')
    form = app.sa_session.query(app.model.FormDefinition).filter_by(
            name=form_name).first()
    default_values = {}

    for field in form.fields:
        default_values[field['name'].lower().replace(' ','_')] = ''



    users = app.sa_session.query(app.model.User).all()
    if users:
        for user in users:
            if not user.form_values_id:
                form_values = app.model.FormValues(form, default_values)
                app.sa_session.add(form_values)
                app.sa_session.flush()
                form_values = app.sa_session.query(app.model.FormValues).filter_by(form_definition_id = form.id).first()
                user.form_values_id = form_values.id
                app.sa_session.flush()

class SimpleApp:
    def __init__(self, db_conn, file_path):
        self.model = galaxy.model.mapping.init(file_path, db_conn, engine_options={},
                                               create_tables=False)
    @property
    def sa_session( self ):
        """
        Returns a SQLAlchemy session -- currently just gets the current
        session from the threadlocal session context, but this is provided
        to allow migration toward a more SQLAlchemy 0.4 style of use.
        """
        return self.model.context.current

if __name__ == "__main__":
    parser = OptionParser()
    (options, args) = parser.parse_args()
    main(*args)
