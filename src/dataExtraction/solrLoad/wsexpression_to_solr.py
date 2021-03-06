#!/usr/bin/env python

# this script takes expression WS objects and creates a tab-delimited import file for solr
import StringIO
import json
import sys
import random
import re

# found at https://pythonadventures.wordpress.com/tag/unicodeencodeerror/
reload(sys)
sys.setdefaultencoding("utf-8")

import biokbase.workspace.client
import biokbase.cdmi.client

wsname = 'KBasePublicExpression'

def export_expression_from_ws(maxNumObjects,expObjIds):
    #ws_client = biokbase.workspace.client.Workspace('http://localhost:7058')
#    ws_client = biokbase.workspace.client.Workspace('http://140.221.84.209:7058')
    ws_client = biokbase.workspace.client.Workspace('https://kbase.us/services/ws')

    # production instance
    cdmi_api = biokbase.cdmi.client.CDMI_API()
    cdmi_entity_api = biokbase.cdmi.client.CDMI_EntityAPI()
    # private instance
    #cdmi_api = biokbase.cdmi.client.CDMI_API('http://192.168.1.163:7032')
    #cdmi_entity_api = biokbase.cdmi.client.CDMI_EntityAPI('http://192.168.1.163:7032')

    genome_entities = cdmi_entity_api.all_entities_Genome(0,15000,['id','scientific_name','source_id'])
    # this Poplar version is not in production central store yet
#    if not genome_entities.has_key('kb|g.3907'):
#        genome_entities['kb|g.3907'] = {'scientific_name':'Populus trichocarpa'}

    # these dicts will be used to cache feature functions from the CDMI
    feature_functions = dict()
    feature_encompasses = dict()
    
    pat = re.compile(r'\s+')

    workspace_object = ws_client.get_workspace_info({'workspace':wsname})
    
    all_workspaces = [ workspace_object ]
    
    #print all_workspaces
    
    # the keys in the solr schema
    # print out a header file
    # data fields must be printed in same order
    solr_ws_keys = ['object_id','workspace_name','object_type', 'object_name']
    solr_keys = [ 'series_id','series_source_id','series_genome_ids','series_sample_ids','series_title','series_summary','series_design','series_publication_id','series_external_source_date','sample_series_ids','sample_id','sample_source_id','sample_type','sample_title','sample_numerical_interpretation','sample_description','sample_data_quality_level','sample_original_median','sample_external_source_date','sample_genome_id','sample_expression_ontology_terms','sample_platform_id','sample_default_control_sample','sample_averaged_from_samples','sample_protocol','sample_strain','sample_strain_wild_type','sample_persons','sample_molecule','sample_data_source','sample_feature_ids','level_feature_id','level_feature_function','level_expression_level']
    headerOutFile = open('expressionToSolr.tab.headers', 'w')
    print >> headerOutFile, "\t".join(solr_ws_keys + solr_keys)
    #print >> headerOutFile, "\n"
    headerOutFile.close()
    
    outFile = open('expressionToSolr.tab', 'w')
    
    # first get all series
    # populate a structure mapping sample ids to series ids

    samples_to_series = dict()
    series_objects = dict()
    feature_objects = dict()

    #for n in all_workspaces:
    for n in all_workspaces:
    
        workspace_id = n[0]
        workspace_name = n[1]

        objects_list = list()

        if len(expObjIds) > 0:
            names_list = list()
            for expObjId in expObjIds:
                names_list.append({'workspace':workspace_name,'name':expObjId})
            objects_list = [x['info'] for x in ws_client.get_objects(names_list)]
        else:
            # then get all samples and propagate series info in sample doc
            # propagate some series and sample info into expression_level doc
            objects_list = ws_client.list_objects({"ids": [workspace_id], "type":"KBaseExpression.ExpressionSeries"})

        if len(objects_list) > 0:
            print "\tWorkspace %s has %d objects" % (workspace_name, len(objects_list))
            object_counter = 0
    
            if maxNumObjects < 1000 :
                objects_list = random.sample(objects_list,maxNumObjects)
    
            for x in objects_list:
                print "\t\tFinished checking %s, done with %s of all objects in %s" % (x[1], str(100.0 * float(object_counter)/len(objects_list)) + " %", workspace_name)
    
                if "ExpressionSeries" in x[2]:
    
                    done = False
    
                    object_type = x[2]
                    object_name = x[1]
    
    #                sys.stderr.write(str(x)+"\n")
                    while not done:
                        try:
# should probably batch retrieving these objects at some point
                            expression = ws_client.get_objects([{"wsid": str(workspace_id), "objid": x[0]}])
                            done = True
                        except Exception, e:
                            print str(e)
                            print "Having trouble getting " + str(x[0]) + " from workspace " + str(workspace_id)
    
                    #print json.dumps(expression['data'], sort_keys=True, indent=4, separators=(',',': '))
                    expression = expression[0]
                    series_path = workspace_name + '/' + object_name
                    series_objects[series_path] = expression['data']
                    #print expression['info']
                    
    # [u'originator', u'comment', u'assay', u'GwasPopulation_obj_id', u'variation_file', u'filetype', u'genome', u'GwasPopulationVariation_obj_id']
    
                    object_id = 'kb|ws.' + str(workspace_id) + '.obj.' + str(expression['info'][0])
    
                    search_values=dict()
                    for key in solr_keys:
                        search_values[key] = ''
    
                    series_scalar_keys = [ 'id','source_id','title','summary','design','publication_id','external_source_date']
    
                    # handle generic scalar fields
                    for key in series_scalar_keys:
                        if expression['data'].has_key(key):
                            search_values['series_'+key] = pat.sub(' ', str(expression['data'][key]))
                        else:
                            search_values['series_'+key]=''

                    series_list_keys = []
                    for key in series_list_keys:
                        if expression['data'].has_key(key):
                            print >> sys.stderr, key
                            print >> sys.stderr, expression['data'][key]
                            search_values['series_'+key] = ' '.join(expression['data'][key])
                        else:
                            search_values['series_'+key]=''

                    # handle special fields
                    if expression['data'].has_key('genome_expression_sample_ids_map'):
                        search_values['series_genome_ids'] = ''
                        for key in expression['data']['genome_expression_sample_ids_map'].keys():
                            search_values['series_genome_ids'] += ' ' + key
                            samples = list()
                            for x in expression['data']['genome_expression_sample_ids_map'][key]:
                                # could also make kb|ws.NN.obj.NNNN ids out of these if we wanted
                                [wsid,objid,ver] = x.split('/')
                                samples.append({'wsid':wsid,'objid':objid})
                            samples_info = ws_client.get_object_info(samples,0)
                            search_values['series_sample_ids'] = ' '
                            for y in samples_info:
                                sample_path=y[7]+'/'+y[1]
                                if not samples_to_series.has_key(sample_path):
                                    samples_to_series[sample_path] = list()
                                samples_to_series[sample_path].append(series_path)
                                search_values['series_sample_ids'] += sample_path + ' ' + y[1] + ' '


                    outBuffer = StringIO.StringIO()
    
                    try:
                        solr_strings = [object_id,workspace_name,object_type,object_name]
                        solr_strings += [ unicode(str(search_values[x])) for x in solr_keys ]
                        solr_line = "\t".join(solr_strings)
                        outBuffer.write(solr_line + "\n")
                    except Exception, e:
                        print str(e)
    #                    print search_values
                        print "Failed trying to write to string buffer."
    
                    outFile.write(outBuffer.getvalue().encode('utf8').replace('\'','').replace('"',''))

                    outBuffer.close()
                else:
                    print '            skipping %s, is a %s' % (x[0], x[2])
                object_counter += 1

#        print >> sys.stderr, samples_to_series

        objects_list = list()

        if len(expObjIds) > 0:
            names_list = list()
            for expObjId in expObjIds:
                names_list.append({'workspace':workspace_name,'name':expObjId})
            objects_list = [x['info'] for x in ws_client.get_objects(names_list)]
        else:
            objects_list = ws_client.list_objects({"ids": [workspace_id],"type":"KBaseExpression.ExpressionSample"})
        if len(objects_list) > 0:
            print "\tWorkspace %s has %d objects" % (workspace_name, len(objects_list))
            object_counter = 0
    
            if maxNumObjects < 1000 :
                objects_list = random.sample(objects_list,maxNumObjects)
    
            for x in objects_list:
                print "\t\tFinished checking %s, done with %s of all objects in %s" % (x[1], str(100.0 * float(object_counter)/len(objects_list)) + " %", workspace_name)
    
                if "ExpressionSample" in x[2]:
    
                    done = False
    
                    object_type = x[2]
                    object_name = x[1]
    
    #                sys.stderr.write(str(x)+"\n")
                    while not done:
                        try:
# should probably batch retrieving these objects at some point
                            expression = ws_client.get_objects([{"wsid": str(workspace_id), "objid": x[0]}])
                            done = True
                        except Exception, e:
                            print str(e)
                            print "Having trouble getting " + str(x[0]) + " from workspace " + str(workspace_id)
    
                    #print json.dumps(expression['data'], sort_keys=True, indent=4, separators=(',',': '))
                    expression = expression[0]
                    #print expression['info']
                    
    # [u'originator', u'comment', u'assay', u'GwasPopulation_obj_id', u'variation_file', u'filetype', u'genome', u'GwasPopulationVariation_obj_id']
    
                    object_id = 'kb|ws.' + str(workspace_id) + '.obj.' + str(expression['info'][0])
    
                    search_values=dict()
                    for key in solr_keys:
                        search_values[key] = ''
    
                    sample_scalar_keys = [ 'id','title','type','external_source_date','numerical_interpretation','description','data_quality_level','original_median','genome_id','platform_id','default_control_sample','molecule','data_source']
    
                    # handle generic scalar fields
                    for key in sample_scalar_keys:
                        if expression['data'].has_key(key):
                            search_values['sample_'+key] = pat.sub(' ', str(expression['data'][key]))
                        else:
                            search_values['sample_'+key]=''

                    # handle generic list fields
                    list_keys = ['averaged_from_samples']
                    for key in list_keys:
                        if expression['data'].has_key(key):
                            print >> sys.stderr, key
                            print >> sys.stderr, expression['data'][key]
                            search_values['sample_'+key] = ' '.join(expression['data'][key])
                        else:
                            search_values['sample_'+key]=''

                    # handle special fields
# to do: translate platform_id to readable id

                    sample_path = x[7]+'/'+x[1]
                    if samples_to_series.has_key(sample_path):
                        for series in samples_to_series[sample_path]:
                            [series_wsname,series_objname] = series.split('/')
                            search_values['sample_series_ids'] += series + ' ' + series_objname + ' '
                            for key in ['summary','design']:
                                if series_objects[series].has_key(key):
                                    search_values['series_'+key] += pat.sub(' ',series_objects[series][key]) + ' '
                            if series_objects[series].has_key('title'):
                                search_values['series_title'] += series_objects[series]['title'] + ' '

                            print >> sys.stderr, series_objects[series]
                    else:
                        print >> sys.stderr, sample_path

                    if expression['data'].has_key('expression_ontology_terms'):
                        for expr in expression['data']['expression_ontology_terms']:
                            search_values['sample_expression_ontology_terms'] = ' '.join(expr.values())

                    if expression['data'].has_key('persons'):
                        for x in expression['data']['persons']:
                            search_values['sample_persons'] += pat.sub(' ',str(x['first_name'] + ' ' + x['last_name'] + ' ' + x['institution']))
                    else:
                        search_values['sample_persons']=''

                    if expression['data'].has_key('protocol'):
                        search_values['sample_protocol'] = pat.sub(' ',str(expression['data']['protocol']['name'] + ' ' + expression['data']['protocol']['description']))
                    else:
                        search_values['sample_protocol']=''

                    if expression['data'].has_key('strain'):
                        search_values['sample_strain'] = expression['data']['strain']['name'] + ' ' + expression['data']['strain']['description'] + ' ' + expression['data']['strain']['genome_id'] + ' reference_strain:' + expression['data']['strain']['reference_strain'] + ' wild_type:' + expression['data']['strain']['wild_type']
                        if expression['data']['strain']['wild_type'] == 'Y':
                            search_values['sample_strain_wild_type'] = True
                        else:
                            search_values['sample_strain_wild_type'] = False
                    else:
                        search_values['sample_strain']=''

                    if expression['data'].has_key('genome_expression_sample_ids_map'):
                        search_values['series_genome_ids'] = ''
                        for key in expression['data']['genome_expression_sample_ids_map'].keys():
                            search_values['series_genome_ids'] += ' ' + key
                            samples = list()
                            for x in expression['data']['genome_expression_sample_ids_map'][key]:
                                # could also make kb|ws.NN.obj.NNNN ids out of these if we wanted
                                [wsid,objid,ver] = x.split('/')
                                samples.append({'wsid':wsid,'objid':objid})
                            samples_info = ws_client.get_object_info(samples,0)
                            search_values['series_sample_ids'] = ' '
                            for x in samples_info:
                                search_values['series_sample_ids'] += x[7]+'/'+x[1] + ' ' + x[1] + ' '

                    outBuffer = StringIO.StringIO()
    
                    search_values['sample_feature_ids'] = ''
                    if expression['data'].has_key('expression_levels'):
                        search_values['sample_feature_ids'] += ' '.join(expression['data']['expression_levels'].keys())

                        # chase down locus-mrna-cds relationship to get functions
                        encompass1 = cdmi_entity_api.get_relationship_IsEncompassedIn(expression['data']['expression_levels'].keys(),[],['to_link'],[])
                        encompass=dict()
                        for feat in encompass1:
                            encompass[feat[1]['from_link']] = feat[1]['to_link']
                        encompass2 = cdmi_entity_api.get_relationship_IsEncompassedIn(encompass.values(),[],['to_link'],[])
                        for feat in encompass2:
                            encompass[feat[1]['from_link']] = feat[1]['to_link']
#                        print >> sys.stderr, encompass
#                        print >> sys.stderr, encompass['kb|g.3899.CDS.62167']
#                        print >> sys.stderr, encompass[encompass['kb|g.3899.CDS.62167']]
                        

# would like to get feature objects here
# add to feature_objects dictionary?
                        objectids = [ {'workspace':'KBasePublicRichGenomesLoad','name':search_values['sample_genome_id'] + '.featureset', 'included':['/features/*/data/function'] } ]
#                        print >> sys.stderr, objectids
                        feature_objects = ws_client.get_object_subset(objectids)
#                        print >> sys.stderr, 'feature_objects'
#                        print >> sys.stderr, feature_objects[0]['data']
#                        print >> sys.stderr, feature_objects.keys()
#                        print >> sys.stderr, 'feature_object trace'
#                        print >> sys.stderr, feature_objects[0]['data']['features'][encompass[encompass['kb|g.3899.CDS.62167']]]['data']


                        for feature_id in expression['data']['expression_levels']:
                            level_search_values = dict()
                            for key in solr_keys:
                                level_search_values[key] = ''
                            level_search_values['object_name'] = object_name + '.' + feature_id
                            level_search_values['workspace_name'] = workspace_name
                            level_search_values['object_type'] = 'KBaseExpression.ExpressionLevel'
                            level_search_values['object_id'] = object_id + '.' + feature_id
                            for key in ['sample_id','sample_series_ids','sample_genome_id']:
                                level_search_values[key] = search_values[key]

                            level_search_values['level_feature_id'] = feature_id
                            level_search_values['level_expression_level'] = expression['data']['expression_levels'][feature_id]

                            level_search_values['level_feature_function'] = feature_objects[0]['data']['features'][encompass[encompass[feature_id]]]['data']['function']

#    solr_ws_keys = ['object_id','workspace_name','object_type', 'object_name']
                            try:
                                solr_strings = [ unicode(str(level_search_values[y])) for y in solr_ws_keys ]
                                solr_strings += [ unicode(str(level_search_values[y])) for y in solr_keys ]
                                solr_line = "\t".join(solr_strings)
                                outBuffer.write(solr_line + "\n")

                                # for debugging only!
                                #outFile.write(outBuffer.getvalue().encode('utf8').replace('\'','').replace('"',''))

                            except Exception, e:
                                print str(e)
            #                    print search_values
                                print "Failed trying to write to string buffer."
    

                    try:
                        solr_strings = [object_id,workspace_name,object_type,object_name]
                        solr_strings += [ unicode(str(search_values[x])) for x in solr_keys ]
                        solr_line = "\t".join(solr_strings)
                        outBuffer.write(solr_line + "\n")
                    except Exception, e:
                        print str(e)
    #                    print search_values
                        print "Failed trying to write to string buffer."
    
                    outFile.write(outBuffer.getvalue().encode('utf8').replace('\'','').replace('"',''))

                    outBuffer.close()
                else:
                    print '            skipping %s, is a %s' % (x[0], x[2])
                object_counter += 1

    outFile.close()
    
if __name__ == "__main__":

    import argparse
    parser = argparse.ArgumentParser(description='Create import files from workspace objects')
    parser.add_argument('--count', action="store", dest="maxNumObjects", type=int)
    parser.add_argument('expObjIds', action="store", nargs='*')
    args = parser.parse_args()

    maxNumObjects = sys.maxint
    if args.maxNumObjects:
        maxNumObjects = args.maxNumObjects
    
    print args.expObjIds
    export_expression_from_ws(maxNumObjects,args.expObjIds)
