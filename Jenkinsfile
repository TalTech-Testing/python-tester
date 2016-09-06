/*
 * Jenkinsfile bootstrapper
 */
node {
    stage "Acquire configuration"
    echo "Checking out configuration..."
    checkout([$class: 'GitSCM', branches: [[name: '*/master']], doGenerateSubmoduleConfigurations: false, extensions: [[$class: 'RelativeTargetDirectory', relativeTargetDir: 'configuration']], submoduleCfg: [], userRemoteConfigs: [[credentialsId: '420c439b-85e1-41e8-87b5-ac7d7b5a54cc', url: 'git@git.ttu.ee:devel/ained/configuration.git']]])
    load 'configuration/jenkins/hodor/Jenkinsfile'
}
