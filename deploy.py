import subprocess
import shutil
import json
import os
import re
import glob


def main():
    environment = os.environ.get('ENV') or 'dev'
    s_environment = os.environ.get('S_ENV') or 'shared'

    print('1. deploy infra')

    print('1.1. deploy shared infra')
    subprocess.run(['terraform', 'init'], cwd='./infra/aws-batch', check=True)
    if not os.path.exists('./infra/aws-batch/terraform.tfstate.d/%s' % s_environment):
        subprocess.run(['terraform', 'workspace', 'new', s_environment], cwd='./infra/aws-batch', check=True)
    subprocess.run(['terraform', 'workspace', 'select', s_environment], cwd='./infra/aws-batch', check=True)
    subprocess.run(['terraform', 'apply', '-var-file=../../terraform.tfvars'], cwd='./infra/aws-batch', check=True)

    print('1.2. deploy infra')

    with open('./infra/aws-batch/terraform.tfstate.d/%s/terraform.tfstate' % s_environment) as f:
        tfstate = json.load(f)
        tfresource = tfstate['modules'][0]['resources']

    job_queue = tfresource['aws_batch_job_queue.otm']['primary']['id']

    for filename in glob.iglob('./infra/common/plugin_*.tf'):
        os.remove(filename)

    for filename in glob.iglob('./plugins/*/infra/*.tf'):
        tfname_base = os.path.split(filename)
        with open(tfname_base[0] + '/../package.json', 'r') as f:
            package = json.load(f)
            plugin_name = package['name']
        os.symlink('../../' + filename, './infra/common/plugin_' + plugin_name + tfname_base[1])

    subprocess.run(['terraform', 'init'], cwd='./infra/common', check=True)
    if not os.path.exists('./infra/common/terraform.tfstate.d/' + environment):
        subprocess.run(['terraform', 'workspace', 'new', environment], cwd='./infra/common', check=True)
    subprocess.run(['terraform', 'workspace', 'select', environment], cwd='./infra/common', check=True)

    vars = ['terraform', 'apply', '-var-file=../../terraform.tfvars',
            '-var=aws_batch_job_queue_arn=%s' % job_queue]
    if os.path.exists('%s-terraform.tfvars' % environment):
        vars.append('-var-file=../../%s-terraform.tfvars' % environment)
    subprocess.run(vars, cwd='./infra/common', check=True)

    with open('./infra/common/terraform.tfstate.d/%s/terraform.tfstate' % environment) as f:
        tfstate = json.load(f)
        tfresource = tfstate['modules'][0]['resources']

    script_bucket = tfresource['aws_s3_bucket.otm_script']['primary']['id']
    client_bucket = tfresource['aws_s3_bucket.otm_client']['primary']['id']
    stat_bucket = tfresource['aws_s3_bucket.otm_stats']['primary']['id']
    config_bucket = tfresource['aws_s3_bucket.otm_config']['primary']['id']
    athena_bucket = tfresource['aws_s3_bucket.otm_athena']['primary']['id']
    collect_log_bucket = tfresource['aws_s3_bucket.otm_collect_log']['primary']['id']

    script_distribution = tfresource['aws_cloudfront_distribution.otm_script_distribution']['primary']['id']
    client_distribution = tfresource['aws_cloudfront_distribution.otm_client_distribution']['primary']['id']

    script_domain = tfresource['aws_cloudfront_distribution.otm_script_distribution']['primary']['attributes'][
        'domain_name']
    if 'aws_route53_record.otm' in tfresource:
        script_domain = tfresource['aws_route53_record.otm']['primary']['attributes']['name']

    collect_domain = tfresource['aws_cloudfront_distribution.otm_collect_distribution']['primary']['attributes'][
        'domain_name']
    if 'aws_route53_record.collect' in tfresource:
        collect_domain = tfresource['aws_route53_record.collect']['primary']['attributes']['name']

    client_domain = tfresource['aws_cloudfront_distribution.otm_client_distribution']['primary']['attributes'][
        'domain_name']
    if 'aws_route53_record.client' in tfresource:
        client_domain = tfresource['aws_route53_record.client']['primary']['attributes']['name']

    dynamo_db_table = tfresource['aws_dynamodb_table.otm_role']['primary']['id']
    dynamo_db_table_arn = tfresource['aws_dynamodb_table.otm_role']['primary']['attributes']['arn']

    job_definition = tfresource['aws_batch_job_definition.otm_data_retriever']['primary']['id']

    sns_topic = tfresource['aws_sns_topic.otm_collect_log_topic']['primary']['attributes']['name']

    athena_database = tfresource['aws_athena_database.otm']['primary']['id']

    cognito_identify_pool_id = tfresource['aws_cognito_identity_pool.otm']['primary']['id']
    cognito_user_pool_id = None
    cognito_user_pool_client_id = None
    aws_id = re.match('^arn:aws:cognito-identity:[a-z0-9\-]+:([0-9]+):identitypool',
                      tfresource['aws_cognito_identity_pool.otm']['primary']['attributes']['arn'])[1]
    for i in tfresource['aws_cognito_identity_pool.otm']['primary']['attributes'].keys():
        v = tfresource['aws_cognito_identity_pool.otm']['primary']['attributes'][i]
        if re.match('^cognito_identity_providers\.[0-9]+\.client_id$', i):
            cognito_user_pool_client_id = v
        if re.match('^cognito_identity_providers\.[0-9]+\.provider_name$', i):
            cognito_user_pool_id = re.match('^cognito-idp\.([a-z0-9\-]+)\.amazonaws.com/(.+)$', v)[2]

    cognito_user_pool_arn = 'arn:aws:cognito-idp:%s:%s:userpool/%s' % (
        os.environ.get('AWS_DEFAULT_REGION'), aws_id, cognito_user_pool_id)

    shutil.copy('./client_apis/.chalice/config.json.sample', './client_apis/.chalice/config.json')
    shutil.copy('./log_formatter/.chalice/config.json.sample', './log_formatter/.chalice/config.json')

    print('2. deploy otm.js')
    subprocess.run(['yarn', 'install'], check=True)
    subprocess.run(['npm', 'run', 'build'], env={'NODE_ENV': 'production', 'PATH': os.environ.get('PATH')}, check=True)
    subprocess.run(['aws', 's3', 'cp', './dist/otm.js', 's3://%s/otm.js' % script_bucket, '--acl=public-read'],
                   check=True)

    print('3. deploy client API')
    with open('./client_apis/.chalice/config.json', 'r') as f:
        config = json.load(f)
        env = config['environment_variables']
        env['OTM_BUCKET'] = script_bucket
        env['OTM_URL'] = 'https://%s/otm.js' % script_domain
        env['COLLECT_URL'] = 'https://%s/collect' % collect_domain
        env['OTM_ROLE_DYNAMODB_TABLE'] = dynamo_db_table
        env['OTM_STATS_BUCKET'] = stat_bucket
        env['OTM_STATS_PREFIX'] = 'stats/'
        env['OTM_SCRIPT_CDN'] = 'https://%s' % script_domain
        env['OTM_COGNITO_USER_POOL_ARN'] = cognito_user_pool_arn
        env['STATS_BATCH_JOB_QUEUE'] = job_queue
        env['STATS_BATCH_JOB_DEFINITION'] = job_definition
        env['STATS_CONFIG_BUCKET'] = config_bucket
        env['STATS_GCLOUD_KEY_NAME'] = 'account.json'
        env['STATS_ATHENA_DATABASE'] = athena_database
        env['STATS_ATHENA_TABLE'] = 'otm_collect2'
        env['STATS_ATHENA_RESULT_BUCKET'] = athena_bucket

        # apply plugin configuration
        for config_file in glob.iglob('./plugins/*/config.json'):
            with open(config_file, 'r') as cf:
                config_data = json.load(cf)
                if 'api' in config_data:
                    for k in config_data['api']:
                        env[k] = config_data['api'][k]

    with open('./client_apis/.chalice/config.json', 'w') as f:
        json.dump(config, f, indent=4)

    import client_apis.install_plugin
    client_apis.install_plugin.main()

    with open('./client_apis/.chalice/policy-sample.json', 'r') as f:
        config = json.load(f)
        config['Statement'][1]['Resource'] = []
        config['Statement'][1]['Resource'].append('arn:aws:s3:::%s/*' % script_bucket)
        config['Statement'][1]['Resource'].append('arn:aws:s3:::%s' % script_bucket)
        config['Statement'][1]['Resource'].append('arn:aws:s3:::%s/*' % stat_bucket)
        config['Statement'][1]['Resource'].append('arn:aws:s3:::%s' % stat_bucket)
        config['Statement'][2]['Resource'][0] = dynamo_db_table_arn

    with open('./client_apis/.chalice/policy-%s.json' % environment, 'w') as f:
        json.dump(config, f, indent=4)

    subprocess.run(['pip', 'install', '-r', 'requirements.txt'], cwd='./client_apis', check=True)
    subprocess.run(['chalice', 'deploy', '--no-autogen-policy', '--stage=%s' % environment], cwd='./client_apis',
                   check=True)

    print('4. deploy data_retriever')

    import data_retriever.install_plugin
    data_retriever.install_plugin.main()

    repository_url = tfresource['aws_ecr_repository.otm_data_retriever']['primary']['attributes']['repository_url']
    p = subprocess.Popen(['aws', 'ecr', 'get-login', '--no-include-email'], stdout=subprocess.PIPE)
    p.wait()
    subprocess.run(p.stdout.readlines()[0].decode('utf-8').split(), check=True)
    subprocess.run(['docker', 'build', '-t', 'otm-data-retriever', '.'], cwd='./data_retriever', check=True)
    subprocess.run(['docker', 'tag', 'otm-data-retriever:latest', '%s:latest' % repository_url], cwd='./data_retriever',
                   check=True)
    subprocess.run(['docker', 'push', '%s:latest' % repository_url], cwd='./data_retriever', check=True)

    print('5. deploy client frontend')
    with open('./client_apis/.chalice/deployed/%s.json' % environment, 'r') as f:
        api_resource = json.load(f)

    subprocess.run(['yarn', 'install'], cwd='./client', check=True)
    subprocess.run(['yarn', 'install-otm-plugin'], cwd='./client', check=True)
    subprocess.run(['npm', 'run', 'build'], env={
        'NODE_ENV': 'production',
        'PATH': os.environ.get('PATH'),
        'API_BASE_URL': api_resource['resources'][2]['rest_api_url'],
        'ASSETS_PUBLIC_PATH': "https://%s/" % client_domain,
        'COGNITO_IDENTITY_POOL_ID': cognito_identify_pool_id,
        'COGNITO_REGION': os.environ.get('AWS_DEFAULT_REGION'),
        'COGNITO_IDENTITY_POOL_REGION': os.environ.get('AWS_DEFAULT_REGION'),
        'COGNITO_USER_POOL_ID': cognito_user_pool_id,
        'COGNITO_USER_POOL_WEB_CLIENT_ID': cognito_user_pool_client_id,
        'COGNITO_COOKIE_STORAGE_DOMAIN': client_domain,
        'COGNITO_COOKIE_SECURE': '1',
        'BASE_PATH': ''
    }, cwd='./client', check=True)
    subprocess.run(['aws', 's3', 'sync', './client/dist/', 's3://%s/' % client_bucket, '--acl=public-read'], check=True)

    print('6. invalidate client / otm.js')
    subprocess.run(
        ['aws', 'cloudfront', 'create-invalidation', '--distribution-id', script_distribution, '--paths', '/otm.js'],
        check=True)
    subprocess.run(
        ['aws', 'cloudfront', 'create-invalidation', '--distribution-id', client_distribution, '--paths', '/',
         '/index.html'], check=True)

    print('7. deploy log_formatter')
    with open('./log_formatter/.chalice/config.json', 'r') as f:
        config = json.load(f)
        env = config['environment_variables']
        env['OTM_REFORM_S3_BUCKET'] = collect_log_bucket
        env['OTM_REFORM_LOG_PREFIX'] = 'formatted/'

    with open('./log_formatter/.chalice/config.json', 'w') as f:
        json.dump(config, f, indent=4)

    with open('./log_formatter/.chalice/policy-sample.json', 'r') as f:
        config = json.load(f)
        config['Statement'][1]['Resource'] = []
        config['Statement'][1]['Resource'].append('arn:aws:s3:::%s/*' % collect_log_bucket)
        config['Statement'][1]['Resource'].append('arn:aws:s3:::%s' % collect_log_bucket)

    with open('./log_formatter/.chalice/policy-%s.json' % environment, 'w') as f:
        json.dump(config, f, indent=4)

    subprocess.run(['pip', 'install', '-r', 'requirements.txt'], cwd='./log_formatter', check=True)
    local_env = os.environ.copy()
    local_env['OTM_LOG_SNS'] = sns_topic
    subprocess.run(['chalice', 'deploy', '--no-autogen-policy', '--stage=%s' % environment], cwd='./log_formatter',
                   env=local_env, check=True)

    print('8. make athena table')
    athena_query = '''
CREATE EXTERNAL TABLE IF NOT EXISTS %s.otm_collect2(
  `datetime` timestamp, 
  `x_edge_location` string, 
  `sc_bytes` string, 
  `c_ip` string, 
  `cs_method` string, 
  `cs_host` string, 
  `cs_uri_stem` string, 
  `cs_status` string, 
  `cs_referer` string, 
  `cs_user_agent` string, 
  `cs_uri_query` string, 
  `cs_cookie` string, 
  `cs_x_edge_result_type` string, 
  `cs_x_edge_request_id` string, 
  `x_host_header` string, 
  `cs_protocol` string, 
  `cs_bytes` string, 
  `time_taken` string, 
  `x_forwarded_for` string, 
  `ssl_protocol` string, 
  `ssl_cipher` string, 
  `x_edge_response_result_type` string, 
  `cs_protocol_version` string, 
  `fle_status` string, 
  `fle_encrypted_fields` string,
  `qs` string
)
PARTITIONED BY ( 
  `org` string, 
  `tid` string,
  `year` int, 
  `month` int, 
  `day` int)
ROW FORMAT SERDE 
  'org.openx.data.jsonserde.JsonSerDe' 
STORED AS INPUTFORMAT 
  'org.apache.hadoop.mapred.TextInputFormat' 
OUTPUTFORMAT 
  'org.apache.hadoop.hive.ql.io.IgnoreKeyTextOutputFormat'
LOCATION
  's3://%s/formatted'
TBLPROPERTIES ('has_encrypted_data'='false')
''' % (athena_database, collect_log_bucket)

    subprocess.run([
        'aws',
        'athena',
        'start-query-execution',
        '--query-string',
        athena_query,
        '--result-configuration',
        'OutputLocation=s3://%s/deploy' % athena_bucket
    ], check=True)

    print("Deployed: https://%s/" % client_domain)


if __name__ == '__main__':
    main()
