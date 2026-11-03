{{- define "argus.name" -}}{{ .Release.Name }}{{- end -}}
{{- define "argus.labels" -}}
app.kubernetes.io/name: argus
app.kubernetes.io/instance: {{ .Release.Name }}
argus/tenant: {{ regexReplaceAll "[^a-z0-9._-]+" (lower .Values.tenant) "-" | trimAll "-._" | trunc 63 | quote }}
{{- end -}}
