# -*- coding: latin-1 -*-
import numpy as np

from openalea.elongwheat import converter, simulation
from openalea.fspmwheat import tools

"""
    fspmwheat.elongwheat_facade
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~

    The module :mod:`fspmwheat.elongwheat_facade` is a facade of the model ElongWheat.

    This module permits to initialize and run the model ElongWheat from a :class:`MTG <openalea.mtg.mtg.MTG>`
    in a convenient and transparent way, wrapping all the internal complexity of the model, and dealing
    with all the tedious initialization and conversion processes.

    :copyright: Copyright 2014-2016 INRA-ECOSYS, see AUTHORS.
    :license: see LICENSE for details.

"""

SHARED_AXES_INPUTS_OUTPUTS_INDEXES = ['plant', 'axis']

SHARED_HIDDENZONES_INPUTS_OUTPUTS_INDEXES = ['plant', 'axis', 'metamer']

SHARED_ELEMENTS_INPUTS_OUTPUTS_INDEXES = ['plant', 'axis', 'metamer', 'organ', 'element']

ELEMENT_TYPES = ('HiddenElement', 'StemElement', 'LeafElement1')

ELEMENTS_DATA_FROM_ORGAN_DATA = {'width', 'diameter'}


class ElongWheatFacade(object):
    """
    The ElongWheatFacade class permits to initialize, run the model ElongWheat
    from a :class:`MTG <openalea.mtg.mtg.MTG>`, and update the MTG and the dataframes
    shared between all models.

    Use :meth:`run` to run the model.
    """

    def __init__(self, shared_mtg, delta_t,
                 model_axes_inputs_df,
                 model_hiddenzones_inputs_df,
                 model_elements_inputs_df,
                 shared_axes_inputs_outputs_df,
                 shared_hiddenzones_inputs_outputs_df,
                 shared_elements_inputs_outputs_df,
                 geometrical_model, phytoT=None, update_parameters=None,
                 update_shared_df=True, option_static=False):
        """
        :param openalea.mtg.mtg.MTG shared_mtg: The MTG shared between all models.
        :param int delta_t: The delta between two runs, in seconds.
        :param pandas.DataFrame model_axes_inputs_df: the inputs of the model at axes scale.
        :param pandas.DataFrame model_hiddenzones_inputs_df: the inputs of the model at hiddenzones scale.
        :param pandas.DataFrame model_elements_inputs_df: the inputs of the model at elements scale.
        :param pandas.DataFrame shared_axes_inputs_outputs_df: the dataframe of inputs and outputs at axes scale shared between all models.
        :param pandas.DataFrame shared_hiddenzones_inputs_outputs_df: the dataframe of inputs and outputs at hiddenzones scale shared between all models.
        :param pandas.DataFrame shared_elements_inputs_outputs_df: the dataframe of inputs and outputs at elements scale shared between all models.
        :param alinea.adel.adel_dynamic.AdelWheatDyn geometrical_model: The model which deals with geometry.
                This model must implement a method `add_metamer(mtg, phytoT, plant_index, axis_label)` to add a metamer to a specific axis of a plant in a MTG.
        :param str phytoT: a csv file generated by adel model
        :param dict update_parameters: A dictionary with the parameters to update, should have the form {'param1': value1, 'param2': value2, ...}.
        :param bool update_shared_df: If `True`  update the shared dataframes at init and at each run (unless stated otherwise)
        :param bool option_static: Whether the model should be run for a static plant architecture
        """

        self._shared_mtg = shared_mtg  #: the MTG shared between all models

        self._simulation = simulation.Simulation(delta_t=delta_t, update_parameters=update_parameters)  #: the simulator to use to run the model

        self.geometrical_model = geometrical_model  #: the model which deals with geometry
        self._phytoT = phytoT  #: dataframe generated by adel and needed by the method add_metamer()

        all_elongwheat_inputs_dict = converter.from_dataframes(model_hiddenzones_inputs_df, model_elements_inputs_df, model_axes_inputs_df)
        self._update_shared_MTG(all_elongwheat_inputs_dict['hiddenzone'], all_elongwheat_inputs_dict['elements'], all_elongwheat_inputs_dict['axes'], option_static)

        self._shared_axes_inputs_outputs_df = shared_axes_inputs_outputs_df  #: the dataframe at axes scale shared between all models
        self._shared_hiddenzones_inputs_outputs_df = shared_hiddenzones_inputs_outputs_df  #: the dataframe at hiddenzones scale shared between all models
        self._shared_elements_inputs_outputs_df = shared_elements_inputs_outputs_df  #: the dataframe at elements scale shared between all models
        self._update_shared_df = update_shared_df
        if self._update_shared_df:
            self._update_shared_dataframes(model_hiddenzones_inputs_df, model_elements_inputs_df, model_axes_inputs_df)

    def run(self, Tair, Tsoil, option_static=False, optimal_growth_option=False, update_shared_df=None):
        """
        Run the model and update the MTG and the dataframes shared between all models.

        :param float Tair: Air temperature at t (degree Celsius)
        :param float Tsoil: Soil temperature at t (degree Celsius)
        :param bool option_static: Whether the model should be run for a static plant architecture
        :param bool optimal_growth_option: if True the model will assume optimal growth conditions
        :param bool update_shared_df: if 'True', update the shared dataframes at this time step.
        """
        self._initialize_model()
        self._simulation.run(Tair, Tsoil, optimal_growth_option)
        self._update_shared_MTG(self._simulation.outputs['hiddenzone'], self._simulation.outputs['elements'], self._simulation.outputs['axes'], option_static)

        if update_shared_df or (update_shared_df is None and self._update_shared_df):
            elongwheat_hiddenzones_outputs_df, elongwheat_elements_outputs_df, elongwheat_SAM_temperature_outputs_df = converter.to_dataframes(self._simulation.outputs)
            self._update_shared_dataframes(elongwheat_hiddenzones_outputs_df, elongwheat_elements_outputs_df, elongwheat_SAM_temperature_outputs_df)

    def _initialize_model(self):
        """
        Initialize the inputs of the model from the MTG shared between all models.
        """
        all_elongwheat_hiddenzones_dict = {}
        all_elongwheat_elements_dict = {}
        all_elongwheat_SAM_temperature_dict = {}
        all_elongwheat_length_dict = {}
        elongwheat_cumulated_internode_length = {}

        for mtg_plant_vid in self._shared_mtg.components_iter(self._shared_mtg.root):
            mtg_plant_index = int(self._shared_mtg.index(mtg_plant_vid))

            # Axis scale
            for mtg_axis_vid in self._shared_mtg.components_iter(mtg_plant_vid):
                mtg_axis_label = self._shared_mtg.label(mtg_axis_vid)
                # if mtg_axis_label != 'MS':
                #     continue
                mtg_axis_properties = self._shared_mtg.get_vertex_property(mtg_axis_vid)

                axis_id = (mtg_plant_index, mtg_axis_label)
                elongwheat_SAM_temperature_inputs_dict = {}

                is_valid_axis = True
                for axis_input_name in simulation.AXIS_INPUTS:
                    if axis_input_name in mtg_axis_properties:
                        # use the input from the MTG
                        elongwheat_SAM_temperature_inputs_dict[axis_input_name] = mtg_axis_properties[axis_input_name]
                    else:
                        is_valid_axis = False
                        break
                if is_valid_axis:
                    all_elongwheat_SAM_temperature_dict[axis_id] = elongwheat_SAM_temperature_inputs_dict
                    # Complete dict of lengths
                    all_elongwheat_length_dict[axis_id] = {}
                    for i in range(mtg_axis_properties['nb_leaves']):
                        all_elongwheat_length_dict[axis_id][i + 1] = {'sheath': [], 'cumulated_internode': []}
                    elongwheat_cumulated_internode_length[axis_id] = []

                # Metamer scale
                for mtg_metamer_vid in self._shared_mtg.components_iter(mtg_axis_vid):
                    mtg_metamer_index = int(self._shared_mtg.index(mtg_metamer_vid))
                    elongwheat_hiddenzone_data_from_mtg_organs_data = {}  # TODO: a voir si c'est toujours utile

                    mtg_metamer_properties = self._shared_mtg.get_vertex_property(mtg_metamer_vid)
                    if 'hiddenzone' in mtg_metamer_properties:

                        hiddenzone_id = (mtg_plant_index, mtg_axis_label, mtg_metamer_index)
                        mtg_hiddenzone_properties = mtg_metamer_properties['hiddenzone']
                        elongwheat_hiddenzone_inputs_dict = {}

                        is_valid_hiddenzone = True
                        for hiddenzone_input_name in simulation.HIDDENZONE_INPUTS:
                            if hiddenzone_input_name in mtg_hiddenzone_properties:
                                # use the input from the MTG
                                elongwheat_hiddenzone_inputs_dict[hiddenzone_input_name] = mtg_hiddenzone_properties[hiddenzone_input_name]
                            elif hiddenzone_input_name in elongwheat_hiddenzone_data_from_mtg_organs_data:
                                elongwheat_hiddenzone_inputs_dict[hiddenzone_input_name] = elongwheat_hiddenzone_data_from_mtg_organs_data[hiddenzone_input_name]
                            else:
                                print('Invalid hiddenzone {}: input {} is missing'.format(hiddenzone_id, hiddenzone_input_name))
                                is_valid_hiddenzone = False
                                break
                        if is_valid_hiddenzone:
                            all_elongwheat_hiddenzones_dict[hiddenzone_id] = elongwheat_hiddenzone_inputs_dict
                            # Complete dict of lengths
                            if mtg_hiddenzone_properties['leaf_is_emerged'] and mtg_hiddenzone_properties['leaf_is_growing']:
                                growing_sheath_length = max(0, mtg_hiddenzone_properties['leaf_L'] - mtg_hiddenzone_properties['lamina_Lmax'])  # TODO: mettre ce calcul ailleurs certainement.
                                all_elongwheat_length_dict[axis_id][mtg_metamer_index]['sheath'].append(growing_sheath_length)
                            if mtg_hiddenzone_properties['internode_is_growing']:
                                elongwheat_cumulated_internode_length[axis_id].append(mtg_hiddenzone_properties['internode_L'])
                                all_elongwheat_length_dict[axis_id][mtg_metamer_index]['cumulated_internode'].extend(elongwheat_cumulated_internode_length[axis_id])
                            else:
                                internode_organ_vid = self._shared_mtg.components_at_scale(mtg_metamer_vid, 4)[0]
                                assert self._shared_mtg.label(internode_organ_vid) == 'internode'
                                internode_element_labels = [self._shared_mtg.label(internode_element) for internode_element in self._shared_mtg.components_at_scale(internode_organ_vid, 5)]
                                if internode_element_labels == ['baseElement', 'topElement']:
                                    all_elongwheat_length_dict[axis_id][mtg_metamer_index]['cumulated_internode'].extend(elongwheat_cumulated_internode_length[axis_id])

                    # Organ scale
                    for mtg_organ_vid in self._shared_mtg.components_iter(mtg_metamer_vid):
                        mtg_organ_label = self._shared_mtg.label(mtg_organ_vid)
                        mtg_organ_properties = self._shared_mtg.get_vertex_property(mtg_organ_vid)
                        if np.nan_to_num(self._shared_mtg.property('length').get(mtg_organ_vid, 0)) == 0:
                            continue
                        if mtg_organ_label == 'blade':
                            elongwheat_hiddenzone_data_from_mtg_organs_data['lamina_Lmax'] = mtg_organ_properties['shape_mature_length']
                            elongwheat_hiddenzone_data_from_mtg_organs_data['leaf_Wmax'] = mtg_organ_properties['shape_max_width']
                        # Element scale
                        for mtg_element_vid in self._shared_mtg.components_iter(mtg_organ_vid):
                            mtg_element_label = self._shared_mtg.label(mtg_element_vid)
                            mtg_element_properties = self._shared_mtg.get_vertex_property(mtg_element_vid)
                            if np.nan_to_num(self._shared_mtg.property('length').get(mtg_element_vid, 0)) == 0:
                                continue
                            if np.isnan(mtg_element_properties.get('age', 0)):
                                mtg_element_properties['age'] = 0.
                            if set(mtg_element_properties).issuperset(simulation.ELEMENT_INPUTS):
                                elongwheat_element_inputs_dict = {}
                                for elongwheat_element_input_name in simulation.ELEMENT_INPUTS:
                                    elongwheat_element_inputs_dict[elongwheat_element_input_name] = mtg_element_properties[elongwheat_element_input_name]
                                element_id = (mtg_plant_index, mtg_axis_label, mtg_metamer_index, mtg_organ_label, mtg_element_label)
                                all_elongwheat_elements_dict[element_id] = elongwheat_element_inputs_dict
                                # Complete dict of lengths
                                if mtg_organ_label == 'sheath' and not mtg_element_properties['is_growing']:
                                    all_elongwheat_length_dict[axis_id][mtg_metamer_index]['sheath'].append(mtg_element_properties['length'])
                                elif mtg_organ_label == 'internode' and not mtg_element_properties['is_growing']:  # This algo won't copy previous internode length for a phytomer without internode
                                    elongwheat_cumulated_internode_length[axis_id].append(mtg_element_properties['length'])
                                    if all_elongwheat_length_dict[axis_id][mtg_metamer_index]['cumulated_internode'] is None:  # if empty for that phytomer, the list of all phytomer lengths is
                                        all_elongwheat_length_dict[axis_id][mtg_metamer_index]['cumulated_internode'].extend(elongwheat_cumulated_internode_length[axis_id])
                                    else:  # only the last internode length is written (case of organs with hidden and visible part)
                                        all_elongwheat_length_dict[axis_id][mtg_metamer_index]['cumulated_internode'].append(mtg_element_properties['length'])

        self._simulation.initialize({'hiddenzone': all_elongwheat_hiddenzones_dict, 'elements': all_elongwheat_elements_dict, 'axes': all_elongwheat_SAM_temperature_dict,
                                     'sheath_internode_lengths': all_elongwheat_length_dict})

    def _update_shared_MTG(self, all_elongwheat_hiddenzones_data_dict, all_elongwheat_elements_data_dict, all_elongwheat_axes_data_dict, option_static=False):
        """
        Update the MTG shared between all models from the inputs or the outputs of the model.

        :param dict all_elongwheat_hiddenzones_data_dict: Elong-Wheat outputs at hidden zone scale
        :param dict all_elongwheat_elements_data_dict: Elong-Wheat outputs at element scale
        :param dict all_elongwheat_axes_data_dict: Elong-Wheat outputs at axes scale
        :param bool option_static: Whether the model should be run for a static plant architecture
        """

        # add the properties if needed
        mtg_property_names = self._shared_mtg.property_names()
        for elongwheat_data_name in set(simulation.HIDDENZONE_INPUTS_OUTPUTS + simulation.ELEMENT_INPUTS_OUTPUTS + simulation.AXIS_INPUTS_OUTPUTS):
            if elongwheat_data_name not in mtg_property_names:
                self._shared_mtg.add_property(elongwheat_data_name)
        if 'hiddenzone' not in mtg_property_names:
            self._shared_mtg.add_property('hiddenzone')

        # add new metamer(s)
        if not option_static:
            axis_to_metamers_mapping = {}
            for metamer_id in sorted(all_elongwheat_elements_data_dict.keys()):
                axis_id = (metamer_id[0], metamer_id[1])
                if axis_id not in axis_to_metamers_mapping:
                    axis_to_metamers_mapping[axis_id] = []
                axis_to_metamers_mapping[axis_id].append(metamer_id[:3])
            for metamer_id in sorted(all_elongwheat_hiddenzones_data_dict.keys()):
                axis_id = (metamer_id[0], metamer_id[1])
                if axis_id not in axis_to_metamers_mapping:
                    axis_to_metamers_mapping[axis_id] = []
                axis_to_metamers_mapping[axis_id].append(metamer_id)

            for mtg_plant_vid in self._shared_mtg.components_iter(self._shared_mtg.root):
                mtg_plant_index = int(self._shared_mtg.index(mtg_plant_vid))
                for mtg_axis_vid in self._shared_mtg.components_iter(mtg_plant_vid):
                    mtg_axis_label = self._shared_mtg.label(mtg_axis_vid)
                    mtg_metamer_ids = set([(mtg_plant_index, mtg_axis_label, int(self._shared_mtg.index(mtg_metamer_vid))) for mtg_metamer_vid in self._shared_mtg.components_iter(mtg_axis_vid)])
                    if (mtg_plant_index, mtg_axis_label) not in axis_to_metamers_mapping:
                        continue
                    new_metamer_ids = set(axis_to_metamers_mapping[(mtg_plant_index, mtg_axis_label)]).difference(mtg_metamer_ids)
                    for _ in new_metamer_ids:
                        self.geometrical_model.add_metamer(self._shared_mtg, self._phytoT, plant=mtg_plant_index, axe=mtg_axis_label)  # Add new metamer with only top and base element
                    # default value to age property in order to run  update_geometry()
                    for mtg_organ_vid in self._shared_mtg.components_at_scale(mtg_axis_vid, 4):
                        if self._shared_mtg.property('label')[mtg_organ_vid] == 'blade':
                            self._shared_mtg.property('age')[mtg_organ_vid] = self._shared_mtg.property('age').get(mtg_organ_vid, 0)

            self.geometrical_model.update_geometry(self._shared_mtg)  # Add HiddenElement and Stem/Leaf Element

        # update the properties of the MTG
        for mtg_plant_vid in self._shared_mtg.components_iter(self._shared_mtg.root):
            mtg_plant_index = int(self._shared_mtg.index(mtg_plant_vid))

            # Axis scale
            for mtg_axis_vid in self._shared_mtg.components_iter(mtg_plant_vid):
                mtg_axis_label = self._shared_mtg.label(mtg_axis_vid)
                axis_id = (mtg_plant_index, mtg_axis_label)
                if axis_id in all_elongwheat_axes_data_dict:
                    elongwheat_axis_data_dict = all_elongwheat_axes_data_dict[axis_id]
                    for axis_data_name, axis_data_value in elongwheat_axis_data_dict.items():
                        self._shared_mtg.property(axis_data_name)[mtg_axis_vid] = axis_data_value

                if option_static:
                    continue

                # metamer scale
                for mtg_metamer_vid in self._shared_mtg.components_iter(mtg_axis_vid):
                    mtg_metamer_index = int(self._shared_mtg.index(mtg_metamer_vid))
                    hiddenzone_id = (mtg_plant_index, mtg_axis_label, mtg_metamer_index)
                    mtg_organs_data_from_elongwheat_hiddenzone_data = {}
                    if hiddenzone_id in all_elongwheat_hiddenzones_data_dict:
                        elongwheat_hiddenzone_data_dict = all_elongwheat_hiddenzones_data_dict[hiddenzone_id]
                        mtg_metamer_properties = self._shared_mtg.get_vertex_property(mtg_metamer_vid)
                        if 'hiddenzone' not in mtg_metamer_properties:
                            self._shared_mtg.property('hiddenzone')[mtg_metamer_vid] = {}

                        for hiddenzone_data_name, hiddenzone_data_value in elongwheat_hiddenzone_data_dict.items():
                            self._shared_mtg.property('hiddenzone')[mtg_metamer_vid][hiddenzone_data_name] = hiddenzone_data_value
                            if hiddenzone_data_name in ('lamina_Lmax', 'leaf_Wmax'):
                                mtg_organs_data_from_elongwheat_hiddenzone_data[hiddenzone_data_name] = hiddenzone_data_value  # To be stored at organ scale (see below)

                    elif 'hiddenzone' in self._shared_mtg.get_vertex_property(mtg_metamer_vid):
                        # remove the 'hiddenzone' property from this metamer
                        del self._shared_mtg.property('hiddenzone')[mtg_metamer_vid]

                    # Organ scale
                    for mtg_organ_vid in self._shared_mtg.components_iter(mtg_metamer_vid):
                        mtg_organ_label = self._shared_mtg.label(mtg_organ_vid)

                        if mtg_organ_label not in ('blade', 'sheath', 'internode'):
                            continue

                        organ_id = (mtg_plant_index, mtg_axis_label, mtg_metamer_index, mtg_organ_label)

                        mtg_organ_properties = self._shared_mtg.get_vertex_property(mtg_organ_vid)
                        mtg_elements_data_from_organ_data = {}
                        # Extract data from organs to be stored at element scale (see below)
                        for organ_data_name in ELEMENTS_DATA_FROM_ORGAN_DATA:
                            if organ_data_name in mtg_organ_properties.keys():
                                mtg_elements_data_from_organ_data[organ_data_name] = mtg_organ_properties[organ_data_name]

                        # Data from hidden zones to be stored at organ scale
                        if mtg_organ_label == 'blade':
                            if len(mtg_organs_data_from_elongwheat_hiddenzone_data) != 0:
                                self._shared_mtg.property('shape_mature_length')[mtg_organ_vid] = mtg_organs_data_from_elongwheat_hiddenzone_data['lamina_Lmax']
                                self._shared_mtg.property('shape_max_width')[mtg_organ_vid] = mtg_organs_data_from_elongwheat_hiddenzone_data['leaf_Wmax']
                            else:
                                blade_id = organ_id + ('LeafElement1',)
                                if blade_id in all_elongwheat_elements_data_dict.keys():
                                    self._shared_mtg.property('shape_mature_length')[mtg_organ_vid] = all_elongwheat_elements_data_dict[organ_id + ('LeafElement1',)]['length']
                                    self._shared_mtg.property('shape_max_width')[mtg_organ_vid] = all_elongwheat_elements_data_dict[organ_id + ('LeafElement1',)]['Wmax']

                        # Update of organ scale from elements dataframe
                        # Organ length should be correct in order to get correct lengths at both organ and element scales after performing the update_geometry()
                        organ_visible_length = all_elongwheat_elements_data_dict.get(organ_id + ('LeafElement1',), {}).get('length', 0.) + \
                                               all_elongwheat_elements_data_dict.get(organ_id + ('StemElement',), {}).get('length', 0.)
                        self._shared_mtg.property('visible_length')[mtg_organ_vid] = organ_visible_length
                        self._shared_mtg.property('age')[mtg_organ_vid] = all_elongwheat_elements_data_dict.get(organ_id + ('LeafElement1',), {}).get('age', 0.)
                        organ_hidden_length = all_elongwheat_elements_data_dict.get(organ_id + ('HiddenElement',), {}).get('length', 0.)
                        total_organ_length = organ_visible_length + organ_hidden_length
                        self._shared_mtg.property('length')[mtg_organ_vid] = total_organ_length

                        # Element scale. Most of the code is temporary, waiting for an update of adel in order that the model could update organ properties from elements.
                        mtg_element_labels = {}
                        for actual_element_vid in self._shared_mtg.components_iter(mtg_organ_vid):
                            actual_element_label = self._shared_mtg.label(actual_element_vid)
                            mtg_element_labels[actual_element_label] = actual_element_vid
                        potential_element_ids = [organ_id + (element_type,) for element_type in ELEMENT_TYPES]
                        for element_id in potential_element_ids:
                            element_label = element_id[-1]
                            if element_id in all_elongwheat_elements_data_dict:
                                elongwheat_element_data_dict = all_elongwheat_elements_data_dict[element_id]
                                # Element just created by elongwheat but not yet in MTG
                                if element_label not in mtg_element_labels.keys():  # MG : This case does not seem to be usefull
                                    if element_label in ('StemElement', 'LeafElement1'):
                                        self._shared_mtg.property('visible_length')[mtg_organ_vid] = elongwheat_element_data_dict['length']
                                    self.geometrical_model.update_geometry(self._shared_mtg)  # Update element scale based on organ infos
                                    mtg_element_vid = [vid for vid in self._shared_mtg.components_iter(mtg_organ_vid) if
                                                       self._shared_mtg.label(vid) == element_label]  # if self._shared_mtg.label(vid) in ('StemElement', 'LeafElement1')
                                    for element_data_name, element_data_value in elongwheat_element_data_dict.items():
                                        self._shared_mtg.property(element_data_name)[mtg_element_vid[0]] = element_data_value

                                # Already existant element
                                else:
                                    mtg_element_vid = mtg_element_labels[element_label]
                                    for element_data_name, element_data_value in elongwheat_element_data_dict.items():
                                        self._shared_mtg.property(element_data_name)[mtg_element_vid] = element_data_value

                                # Put some properties from organ scale at element scale
                                for organ_data_name in mtg_elements_data_from_organ_data:
                                    self._shared_mtg.property(organ_data_name)[mtg_element_vid] = mtg_elements_data_from_organ_data[organ_data_name]

                        # # update of organ scale from elements
                        # new_mtg_element_labels = {}
                        # for new_element_vid in self._shared_mtg.components_iter(mtg_organ_vid):
                        #     new_element_label = self._shared_mtg.label(new_element_vid)
                        #     new_mtg_element_labels[new_element_label] = new_element_vid
                        #
                        # if mtg_organ_label == 'blade' and 'LeafElement1' in new_mtg_element_labels.keys():
                        #     organ_visible_length = self._shared_mtg.property('length')[new_mtg_element_labels['LeafElement1']]
                        #     self._shared_mtg.property('visible_length')[mtg_organ_vid] = organ_visible_length
                        #     self._shared_mtg.property('age')[mtg_organ_vid] = self._shared_mtg.property('age').get(new_mtg_element_labels['LeafElement1'], 0)
                        # elif mtg_organ_label in ('sheath', 'internode') and 'StemElement' in new_mtg_element_labels.keys():
                        #     organ_visible_length = self._shared_mtg.property('length')[new_mtg_element_labels['StemElement']]
                        #     self._shared_mtg.property('visible_length')[mtg_organ_vid] = organ_visible_length
                        # else:
                        #     organ_visible_length = 0
                        #
                        # if 'HiddenElement' in new_mtg_element_labels.keys():
                        #     organ_hidden_length = self._shared_mtg.property('length')[new_mtg_element_labels['HiddenElement']]
                        # else:
                        #     organ_hidden_length = 0
                        #
                        # total_organ_length = organ_visible_length + organ_hidden_length
                        # self._shared_mtg.property('length')[mtg_organ_vid] = total_organ_length

    def _update_shared_dataframes(self, elongwheat_hiddenzones_data_df, elongwheat_elements_data_df, elongwheat_axes_data_df):
        """
        Update the dataframes shared between all models from the inputs dataframes or the outputs dataframes of the model.

        :param pandas.DataFrame elongwheat_hiddenzones_data_df: Elong-Wheat shared dataframe at hidden zone scale
        :param pandas.DataFrame elongwheat_elements_data_df: Elong-Wheat shared dataframe at element scale
        :param pandas.DataFrame elongwheat_axes_data_df: Elong-Wheat shared dataframe at axes scale
        """

        for elongwheat_data_df, \
            shared_inputs_outputs_indexes, \
            shared_inputs_outputs_df in ((elongwheat_hiddenzones_data_df, SHARED_HIDDENZONES_INPUTS_OUTPUTS_INDEXES, self._shared_hiddenzones_inputs_outputs_df),
                                         (elongwheat_elements_data_df, SHARED_ELEMENTS_INPUTS_OUTPUTS_INDEXES, self._shared_elements_inputs_outputs_df),
                                         (elongwheat_axes_data_df, SHARED_AXES_INPUTS_OUTPUTS_INDEXES, self._shared_axes_inputs_outputs_df)):
            tools.combine_dataframes_inplace(elongwheat_data_df, shared_inputs_outputs_indexes, shared_inputs_outputs_df)
